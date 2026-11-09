"""Update service: move one FC site to the newest bench of its bench group.

This layer has no CLI dependency, so the TUI can reuse it. It never prompts. Every FC
request goes to the team of the site only. The only write is `start()`.

FC returns the name of the new `Site Update` record from the update request. The watch
reads that record by name (`press.api.client.get`). The record shows the status and the
steps of all FC jobs of the update (deactivate, backup, update, restore, recover,
activate) in one list.

A failed update is not final at once: FC then starts its recover job, which restores the
site to the old bench. So the watch keeps going through Failure and Recovering. It ends at
Success, Recovered, Fatal or Cancelled, or when the record stays at Failure with no recover
job for FAILURE_LIMIT_SECONDS.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from typing import Any

from fc_manager.api.client import FCClient
from fc_manager.errors import UpdateFailed, UpdateUnknown, UsageError
from fc_manager.inventory import Site
from fc_manager.migrate import IN_PROGRESS, JobStep, parse_running_jobs
from fc_manager.redact import redact

UPDATE_METHOD = "press.api.site.update"
RECORD_DOCTYPE = "Site Update"
# fcm updates a site only in these states. FC itself does not check the status; an update
# deactivates and moves the site, so a Broken site must be fixed first (design D3).
UPDATE_STATUSES = ("Active", "Inactive")
POLL_SECONDS = 2.0
# A record at Failure with no recover job for this long ends the watch (design D1).
FAILURE_LIMIT_SECONDS = 600.0
OUTPUT_CHARS = 500
SHORT_HASH = 7

# Record status -> watch stage.
STAGES = {
    "Pending": "waiting",
    "Scheduled": "waiting",
    "Running": "running",
    "Failure": "failure",
    "Recovering": "recovering",
    "Success": "success",
    "Recovered": "recovered",
    "Fatal": "fatal",
    "Cancelled": "cancelled",
}
FINAL_STAGES = ("success", "recovered", "fatal", "cancelled")


class NothingToUpdate(Exception):  # noqa: N818 - a signal, not an error
    """FC reports no update for the site. Not an error: exit 0 (design D4)."""

    def __init__(self, site: Site) -> None:
        super().__init__(f"Site {site.name} has no update")
        self.site = site


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _flag(value: Any) -> bool:
    return str(value).lower() in ("1", "true")


def _version(tag: Any, commit: Any) -> str:
    """The release tag, else the short commit hash."""
    text = _str(tag)
    if text:
        return text
    commit = _str(commit)
    return commit[:SHORT_HASH]


# --- data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class AppChange:
    app: str
    title: str
    current_version: str
    next_version: str
    current_branch: str
    branch: str
    branch_changes: bool
    update_available: bool


@dataclass(frozen=True)
class UpdateInfo:
    update_available: bool
    apps: tuple[AppChange, ...] = ()

    @property
    def changes(self) -> tuple[AppChange, ...]:
        """Only the apps with an update."""
        return tuple(a for a in self.apps if a.update_available)


@dataclass(frozen=True)
class UpdatePlan:
    site: Site
    status: str  # the site status on FC at the check
    apps: tuple[AppChange, ...] = ()  # the apps with an update
    skip_failing_patches: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.site.name,
            "skip_failing_patches": self.skip_failing_patches,
            "skip_backups": False,  # fcm never skips the FC backup
        }


@dataclass(frozen=True)
class UpdateState:
    """One look at an update record. `stage` is one of: waiting, running, failure,
    recovering, success, recovered, fatal, cancelled."""

    stage: str
    record: str = ""
    status: str = ""
    steps: tuple[JobStep, ...] = ()
    source_bench: str = ""
    destination_bench: str = ""
    recover_job: str = ""
    site_status: str = ""  # read once after the update ends
    checked_at: float = field(default=0.0, compare=False)
    polls: int = field(default=0, compare=False)

    @property
    def final(self) -> bool:
        return self.stage in FINAL_STAGES

    @property
    def failed_step(self) -> JobStep | None:
        return next((s for s in self.steps if s.status == "Failure"), None)

    @property
    def current_step(self) -> JobStep | None:
        running = next((s for s in self.steps if s.status == "Running"), None)
        return running or next((s for s in self.steps if s.status == "Pending"), None)


# --- parsers --------------------------------------------------------------------------


def parse_app_change(row: dict[str, Any]) -> AppChange:
    current_branch = _str(row.get("current_branch"))
    branch = _str(row.get("branch"))
    changes = _flag(row.get("will_branch_change")) or (
        bool(current_branch) and bool(branch) and current_branch != branch
    )
    return AppChange(
        app=_str(row.get("app")),
        title=_str(row.get("title")) or _str(row.get("app")),
        current_version=_version(row.get("current_tag"), row.get("current_hash")),
        next_version=_version(row.get("next_tag"), row.get("next_hash")),
        current_branch=current_branch,
        branch=branch,
        branch_changes=changes,
        update_available=_flag(row.get("update_available")),
    )


def parse_update_info(data: Any) -> UpdateInfo:
    data = data if isinstance(data, dict) else {}
    rows = data.get("apps") if isinstance(data.get("apps"), list) else []
    apps = tuple(parse_app_change(r) for r in rows if isinstance(r, dict) and r.get("app"))
    return UpdateInfo(update_available=_flag(data.get("update_available")), apps=apps)


def _step_status(value: Any) -> str:
    text = _str(value)
    return "Pending" if text == "Undelivered" else text


def parse_update_record(data: Any) -> UpdateState:
    data = data if isinstance(data, dict) else {}
    status = _str(data.get("status"))
    steps = tuple(
        JobStep(
            step=_str(s.get("title")) or _str(s.get("stage")) or _str(s.get("name")),
            status=_step_status(s.get("status")),
            duration=_str(s.get("duration")),
            output=redact(_str(s.get("output")).strip())[-OUTPUT_CHARS:],
        )
        for s in data.get("steps") or []
        if isinstance(s, dict)
    )
    return UpdateState(
        stage=STAGES.get(status, "running"),
        record=_str(data.get("name")),
        status=status,
        steps=steps,
        source_bench=_str(data.get("source_bench")),
        destination_bench=_str(data.get("destination_bench")),
        recover_job=_str(data.get("recover_job")),
    )


# --- service --------------------------------------------------------------------------


class UpdateService:
    def __init__(self, client: FCClient) -> None:
        self.client = client

    def _call(self, site: Site, method: str, **params: Any) -> Any:
        return self.client.call(method, team=site.team.name, **params)

    def site_status(self, site: Site) -> str:
        data = self._call(site, "press.api.site.get", name=site.name)
        return _str(data.get("status")) if isinstance(data, dict) else ""

    def info(self, site: Site) -> UpdateInfo:
        return parse_update_info(
            self._call(site, "press.api.site.check_for_updates", name=site.name)
        )

    def record(self, site: Site, name: str) -> UpdateState:
        return parse_update_record(
            self._call(site, "press.api.client.get", doctype=RECORD_DOCTYPE, name=name)
        )

    def check(self, site: Site, *, skip_failing_patches: bool = False) -> UpdatePlan:
        """Raise NothingToUpdate when FC has no update. Refuse a site that fcm does not
        update, or that has a job in progress."""
        info = self.info(site)
        if not info.update_available:
            raise NothingToUpdate(site)
        status = self.site_status(site)
        if status not in UPDATE_STATUSES:
            raise UsageError(
                f"fcm does not update a site in the {status or 'unknown'} status: {site.name}",
                target=f"site {site.name}",
                hint=f"fcm updates a site that is {' or '.join(UPDATE_STATUSES)}. "
                "This rule is stricter than FC: fix the site first (for example with "
                f"fcm site-migrate {site.name}).",
            )
        jobs = parse_running_jobs(self._call(site, "press.api.site.running_jobs", name=site.name))
        busy = [j for j in jobs if j.status in IN_PROGRESS]
        if busy:
            job = busy[0]
            raise UsageError(
                f"FC has a {job.job_type} job in the {job.status} state on site {site.name}",
                target=f"site {site.name}",
                hint=f"Wait until it ends. Run: fcm site-show {site.name}",
            )
        return UpdatePlan(
            site=site,
            status=status,
            apps=info.changes,
            skip_failing_patches=skip_failing_patches,
        )

    def start(self, plan: UpdatePlan) -> str:
        """The only write: send the update. FC returns the name of the update record."""
        site = plan.site
        name = self.client.write(UPDATE_METHOD, team=site.team.name, **plan.payload())
        if not isinstance(name, str) or not name.strip():
            raise UpdateUnknown(
                f"FC accepted the update of site {site.name}, but its answer holds no update "
                "record name. The update state on FC is not known.",
                target=f"site {site.name}",
                hint=f"Run: fcm site-show {site.name}",
            )
        return name.strip()

    def watch(
        self,
        plan: UpdatePlan,
        record: str,
        sleep: Callable[[float], None],
        poll_seconds: float = POLL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> Iterator[UpdateState]:
        """Follow the update record until the update ends. Yield one state after every poll
        that FC answered, also when nothing changed.

        Raises UpdateFailed when the update ends in Recovered, Fatal or Cancelled, or stays
        at Failure with no recover job for FAILURE_LIMIT_SECONDS."""
        site = plan.site
        polls = 0
        failure_since: float | None = None

        def answered(state: UpdateState) -> UpdateState:
            nonlocal polls
            polls += 1
            return replace(state, checked_at=clock(), polls=polls)

        while True:
            state = self.record(site, record)
            if state.final:
                break
            if state.stage == "failure" and not state.recover_job:
                now = clock()
                if failure_since is None:
                    failure_since = now
                if now - failure_since >= FAILURE_LIMIT_SECONDS:
                    break
            else:
                failure_since = None
            yield answered(state)
            sleep(poll_seconds)

        final = replace(state, site_status=self.site_status(site))
        yield answered(final)
        if final.stage == "success":
            return
        step = final.failed_step
        label = step.label if step else None
        status_hint = f"Site status on FC: {final.site_status or 'unknown'}. "
        show = f"Run: fcm site-show {site.name}"
        if final.stage == "recovered":
            message = (
                f"The update failed on FC at {label or 'an update step'}. "
                "FC restored the site to the old bench."
            )
            hint = status_hint + show
        elif final.stage == "fatal":
            message = (
                f"The update failed on FC at {label or 'an update step'}. "
                "FC could not restore the site."
            )
            hint = status_hint + "Contact FC support. " + show
        elif final.stage == "cancelled":
            message = "The update was cancelled on FC."
            hint = status_hint + show
        else:  # failure with no recover job past the limit
            message = (
                f"The update failed on FC at {label or 'an update step'}, and FC started no "
                f"recovery in {int(FAILURE_LIMIT_SECONDS // 60)} minutes."
            )
            hint = status_hint + show
        raise UpdateFailed(
            message,
            step=label,
            outcome="failure" if final.stage == "failure" else final.stage,
            target=f"site {site.name}",
            server_message=(step.output if step else "") or None,
            hint=hint,
        )
