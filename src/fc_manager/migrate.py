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
from dataclasses import dataclass, replace
from typing import Any

from fc_manager.api.client import FCClient
from fc_manager.errors import FcmError, MigrateFailed, MigrateUnknown, UsageError
from fc_manager.inventory import Site
from fc_manager.jobs import (  # noqa: F401 - re-exported for the callers of migrate
    IN_PROGRESS,
    JOB_DONE,
    POLL_SECONDS,
    JobRow,
    JobSpec,
    JobState,
    JobStep,
    SiteJobWatch,
    _str,
    parse_job,
    parse_running_jobs,
)

MIGRATE_METHOD = "press.api.site.migrate"
JOB_TYPE = "Migrate Site"
# FC lets a migrate run only in these site states (press Site.migrate, @site_action).
MIGRATE_STATUSES = ("Active", "Inactive", "Broken")
# After FC accepts the request, the new job must show up within this time.
FIND_LIMIT_SECONDS = 120.0


# --- data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class MigratePlan:
    site: Site
    status: str  # the site status on FC at the check
    skip_failing_patches: bool = False

    def payload(self) -> dict[str, Any]:
        return {"name": self.site.name, "skip_failing_patches": self.skip_failing_patches}


MigrateState = JobState  # one look at a migrate: the shared job state of jobs.py


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
        return watch_site_job(
            self,
            plan.site,
            job_type=JOB_TYPE,
            word="migrate",
            unknown=MigrateUnknown,
            failed=MigrateFailed,
            sleep=sleep,
            poll_seconds=poll_seconds,
            clock=clock,
        )


def watch_site_job(
    service: MigrateService,
    site: Site,
    *,
    job_type: str,
    word: str,
    unknown: type[FcmError],
    failed: type[FcmError],
    sleep: Callable[[float], None],
    poll_seconds: float = POLL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[MigrateState]:
    """Follow the new `job_type` job of `site` with the shared `SiteJobWatch`, and yield
    the state of that job. Shared by the migrate and the install watch. `word` names the
    action in the messages ("migrate", "install").

    Raises `unknown` when no such job shows up in FIND_LIMIT_SECONDS, and `failed` (with
    the failed step) when the job fails."""
    spec = JobSpec(expected=(job_type,), find_limit=FIND_LIMIT_SECONDS)
    watch = SiteJobWatch(service, site, spec, clock)
    while True:
        state = watch.poll()
        if state.stage == "unknown":
            raise unknown(
                f"FC accepted the {word}, but fcm did not see {_article(word)} {word} job for "
                f"site {site.name}. The result is not known.",
                target=f"site {site.name}",
                hint=f"Site status on FC: {state.site_status or 'unknown'}. "
                f"Run: fcm site-show {site.name}",
            )
        job = state.expected or MigrateState(stage="finding")
        look = replace(
            job,
            stage=state.stage if state.final else job.stage if state.expected else "finding",
            site_status=state.site_status if state.final else "",
            checked_at=state.checked_at,
            polls=state.polls,
        )
        yield look
        if state.final:
            break
        sleep(poll_seconds)
    if look.stage == "failure":
        step = look.failed_step
        raise failed(
            f"The {word} failed on FC at {step.label if step else f'the {word} job'}",
            step=step.label if step else None,
            target=f"site {site.name}",
            server_message=(step.output if step else "") or None,
            hint=f"Site status on FC: {look.site_status or 'unknown'}. "
            f"Run: fcm site-show {site.name}",
        )


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"
