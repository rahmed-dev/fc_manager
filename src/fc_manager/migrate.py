"""Migrate service: run `bench migrate` on one FC site through the FC migrate job.

This layer has no CLI dependency, so the TUI can reuse it. It never prompts. Every FC
request goes to the team of the site only. The only write is `start()`.

FC returns nothing from the migrate request, so the watch finds the job itself: it polls
the running jobs of the site until a "Migrate Site" job shows up. The check before the
request refuses a site with a job in progress, so that job is the one this request made.

FC has no job list that works over GET: `press.api.site.jobs` and `press.api.client.get_list`
both fail on the filters string (HTTP 500, AttributeError; spike runs of 2026-11-09).
`press.api.site.running_jobs` takes a plain site name and works. It shows only Pending and
Running jobs, so a migrate that starts and ends between 2 polls is not seen: the watch
then reports that the result is not known.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from typing import Any

from fc_manager.api.client import FCClient
from fc_manager.errors import MigrateFailed, MigrateUnknown, UsageError
from fc_manager.inventory import Site
from fc_manager.redact import redact

MIGRATE_METHOD = "press.api.site.migrate"
JOB_TYPE = "Migrate Site"
# FC lets a migrate run only in these site states (press Site.migrate, @site_action).
MIGRATE_STATUSES = ("Active", "Inactive", "Broken")
IN_PROGRESS = ("Pending", "Running", "Undelivered")
JOB_DONE = ("Success", "Failure")
POLL_SECONDS = 2.0
# After FC accepts the request, the new job must show up within this time.
FIND_LIMIT_SECONDS = 120.0
OUTPUT_CHARS = 500


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _status(value: Any) -> str:
    """FC shows an "Undelivered" job as "Pending" in its dashboard. So does fcm."""
    text = _str(value)
    return "Pending" if text == "Undelivered" else text


# --- data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class JobRow:
    name: str
    job_type: str
    status: str


@dataclass(frozen=True)
class JobStep:
    step: str
    status: str
    duration: str
    output: str = ""

    @property
    def label(self) -> str:
        return self.step


@dataclass(frozen=True)
class MigratePlan:
    site: Site
    status: str  # the site status on FC at the check
    skip_failing_patches: bool = False

    def payload(self) -> dict[str, Any]:
        return {"name": self.site.name, "skip_failing_patches": self.skip_failing_patches}


@dataclass(frozen=True)
class MigrateState:
    """One look at a migrate. `stage` is one of: finding (FC accepted the request; the
    new job is not visible yet), waiting (the job is queued), running, success, failure."""

    stage: str
    job: str = ""
    status: str = ""
    steps: tuple[JobStep, ...] = ()
    site_status: str = ""  # read once after the job ends
    # Liveness of the watch: when FC last answered, and how many polls ran.
    checked_at: float = field(default=0.0, compare=False)
    polls: int = field(default=0, compare=False)

    @property
    def final(self) -> bool:
        return self.stage in ("success", "failure")

    @property
    def failed_step(self) -> JobStep | None:
        return next((s for s in self.steps if s.status == "Failure"), None)

    @property
    def current_step(self) -> JobStep | None:
        running = next((s for s in self.steps if s.status == "Running"), None)
        return running or next((s for s in self.steps if s.status == "Pending"), None)


# --- parsers --------------------------------------------------------------------------


def parse_running_jobs(data: Any) -> list[JobRow]:
    """`press.api.site.running_jobs` rows: FC puts the job name in `id` and the job type in
    `name`."""
    rows = data if isinstance(data, list) else []
    return [
        JobRow(
            name=_str(r.get("id")), job_type=_str(r.get("name")), status=_status(r.get("status"))
        )
        for r in rows
        if isinstance(r, dict) and r.get("id")
    ]


def parse_job(data: Any) -> MigrateState:
    data = data if isinstance(data, dict) else {}
    status = _status(data.get("status"))
    steps = tuple(
        JobStep(
            step=_str(s.get("step_name")),
            status=_status(s.get("status")),
            duration=_str(s.get("duration")),
            output=redact(_str(s.get("output")).strip())[-OUTPUT_CHARS:],
        )
        for s in data.get("steps") or []
        if isinstance(s, dict)
    )
    stage = {
        "Success": "success",
        "Failure": "failure",
        "Running": "running",
        "Pending": "waiting",
    }.get(status, "running")
    return MigrateState(stage=stage, job=_str(data.get("name")), status=status, steps=steps)


# --- service --------------------------------------------------------------------------


class MigrateService:
    def __init__(self, client: FCClient) -> None:
        self.client = client

    def _call(self, site: Site, method: str, **params: Any) -> Any:
        return self.client.call(method, team=site.team.name, **params)

    def site_status(self, site: Site) -> str:
        data = self._call(site, "press.api.site.get", name=site.name)
        return _str(data.get("status")) if isinstance(data, dict) else ""

    def running_jobs(self, site: Site) -> list[JobRow]:
        """The Pending and Running FC jobs of the site."""
        return parse_running_jobs(self._call(site, "press.api.site.running_jobs", name=site.name))

    def job(self, site: Site, name: str) -> MigrateState:
        return parse_job(self._call(site, "press.api.site.job", job=name))

    def check(self, site: Site, *, skip_failing_patches: bool = False) -> MigratePlan:
        """Refuse a site that FC does not migrate now, or that has a job in progress."""
        status = self.site_status(site)
        if status not in MIGRATE_STATUSES:
            raise UsageError(
                f"FC does not migrate a site in the {status or 'unknown'} status: {site.name}",
                target=f"site {site.name}",
                hint=f"FC migrates a site that is {', '.join(MIGRATE_STATUSES)}.",
            )
        busy = [j for j in self.running_jobs(site) if j.status in IN_PROGRESS]
        if busy:
            job = busy[0]
            raise UsageError(
                f"FC has a {job.job_type} job in the {job.status} state on site {site.name}",
                target=f"site {site.name}",
                hint=f"Wait until it ends. Run: fcm site-show {site.name}",
            )
        return MigratePlan(site=site, status=status, skip_failing_patches=skip_failing_patches)

    def start(self, plan: MigratePlan) -> None:
        """The only write: send the migrate. FC returns nothing."""
        self.client.write(MIGRATE_METHOD, team=plan.site.team.name, **plan.payload())

    def watch(
        self,
        plan: MigratePlan,
        sleep: Callable[[float], None],
        poll_seconds: float = POLL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> Iterator[MigrateState]:
        """Follow the migrate of `plan` until its job ends. Yield one state after every poll
        that FC answered, also when nothing changed.

        Raises MigrateUnknown when no migrate job shows up in FIND_LIMIT_SECONDS, and
        MigrateFailed when the job fails."""
        site = plan.site
        polls = 0

        def answered(state: MigrateState) -> MigrateState:
            nonlocal polls
            polls += 1
            return replace(state, checked_at=clock(), polls=polls)

        started = clock()
        job = ""
        while not job:
            found = [j for j in self.running_jobs(site) if j.job_type == JOB_TYPE]
            if found:
                job = found[0].name
                break
            if clock() - started >= FIND_LIMIT_SECONDS:
                status = self.site_status(site)
                raise MigrateUnknown(
                    f"FC accepted the migrate, but fcm did not see a migrate job for site "
                    f"{site.name}. The result is not known.",
                    target=f"site {site.name}",
                    hint=f"Site status on FC: {status or 'unknown'}. "
                    f"Run: fcm site-show {site.name}",
                )
            yield answered(MigrateState(stage="finding"))
            sleep(poll_seconds)

        while True:
            state = self.job(site, job)
            if state.status in JOB_DONE:
                break
            yield answered(state)
            sleep(poll_seconds)

        final = replace(state, site_status=self.site_status(site))
        yield answered(final)
        if final.stage == "failure":
            step = final.failed_step
            raise MigrateFailed(
                f"The migrate failed on FC at {step.label if step else 'the migrate job'}",
                step=step.label if step else None,
                target=f"site {site.name}",
                server_message=(step.output if step else "") or None,
                hint=f"Site status on FC: {final.site_status or 'unknown'}. "
                f"Run: fcm site-show {site.name}",
            )
