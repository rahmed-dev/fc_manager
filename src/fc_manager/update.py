"""Update service: move one FC site to the newest bench of its bench group.

This layer has no CLI dependency, so the TUI can reuse it. It never prompts. Every FC
request goes to the team of the site only. The only write is `start()`.

The watch is the shared site job watch (jobs.py): it follows the "Update Site Migrate" or
"Update Site Pull" job of the site, and the other jobs around it (backup, recover). A failed
update is not final at once: FC then starts its recover job, which restores the site to the
old bench. The recover job or the site status tells what FC did with the site (design D3).
The `Site Update` record is not read (site-job-finder, design D6).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from fc_manager.api.client import FCClient
from fc_manager.errors import UpdateFailed, UpdateUnknown, UsageError
from fc_manager.inventory import Site
from fc_manager.jobs import (
    IN_PROGRESS,
    POLL_SECONDS,
    RECOVERY_LIMIT_SECONDS,
    UPDATE_JOB_TYPES,
    JobSpec,
    SiteJobReader,
    SiteJobWatch,
    WatchState,
    parse_running_jobs,
)

UPDATE_METHOD = "press.api.site.update"
# fcm updates a site only in these states. FC itself does not check the status; an update
# deactivates and moves the site, so a Broken site must be fixed first (design D3).
UPDATE_STATUSES = ("Active", "Inactive")
FIND_LIMIT_SECONDS = 120.0  # no update job in this time: the result is not known
SHORT_HASH = 7


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


UpdateState = WatchState  # one look at the jobs of the site during an update


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
        """The only write: send the update. FC returns the name of the update record; the
        answer can hold no name, then this returns "" and the watch still runs (D6)."""
        site = plan.site
        name = self.client.write(UPDATE_METHOD, team=site.team.name, **plan.payload())
        return name.strip() if isinstance(name, str) else ""

    def watch(
        self,
        plan: UpdatePlan,
        sleep: Callable[[float], None],
        poll_seconds: float = POLL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> Iterator[UpdateState]:
        """Follow the update jobs of the site until the update ends. Yield one state after
        every poll that FC answered, also when nothing changed.

        Raises UpdateUnknown when no update job shows up in the find limit, and
        UpdateFailed when the update job fails (with what FC did with the site)."""
        site = plan.site
        spec = JobSpec(expected=UPDATE_JOB_TYPES, find_limit=FIND_LIMIT_SECONDS, recover=True)
        watch = SiteJobWatch(SiteJobReader(self.client), site, spec, clock)
        final = None
        for state in watch.run(sleep, poll_seconds):
            yield state
            final = state
        assert final is not None
        raise_update_result(site, final)


def raise_update_result(site: Site, final: UpdateState) -> None:
    """Raise the error for a final update state that is not success. Shared by
    `site-update` and the site results of `bench-deploy`."""
    show = f"Run: fcm site-show {site.name}"
    status_hint = f"Site status on FC: {final.site_status or 'unknown'}. "
    if final.stage == "success":
        return
    if final.stage == "unknown":
        raise UpdateUnknown(
            f"FC accepted the update, but fcm did not see an update job for site {site.name}. "
            "The result is not known.",
            target=f"site {site.name}",
            hint=status_hint + show,
        )
    job = final.expected.job_type if final.expected else "the update job"
    step = final.failed_step
    where = f"{job}, step {step.label}" if step else job
    if final.stage == "recovered":
        message = f"The update failed on FC at {where}. FC restored the site to the old bench."
        hint = status_hint + show
    elif final.stage == "fatal":
        message = f"The update failed on FC at {where}. FC could not restore the site."
        hint = status_hint + "Contact FC support. " + show
    else:  # failure with no recovery seen in the limit
        message = (
            f"The update failed on FC at {where}, and FC started no recovery in "
            f"{int(RECOVERY_LIMIT_SECONDS // 60)} minutes."
        )
        hint = status_hint + show
    raise UpdateFailed(
        message,
        step=step.label if step else None,
        outcome="failure" if final.stage == "failure" else final.stage,
        target=f"site {site.name}",
        server_message=(step.output if step else "") or None,
        hint=hint,
    )
