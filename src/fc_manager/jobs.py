"""The FC jobs of one site, and the one watch that all site actions share.

`site-migrate`, `site-install-app`, `site-update` and `bench-deploy` follow their site
jobs with `SiteJobWatch`. Each poll (every POLL_SECONDS, 2 s) reads:
- `press.api.site.running_jobs`: the Pending and Running jobs of the site;
- `press.api.site.job`: the steps of each followed job that is not done;
- `press.api.site.get`: the site status, after the expected job ends, and in the recovery
  step of a failed update.

Short-job limit: FC has no job list that works over GET (`press.api.site.jobs` and
`press.api.client.get_list` fail on the filters string; spike runs of 2026-11-09), and
`running_jobs` lists only the Pending and Running jobs. A job that starts and ends between
two polls is not seen. When that job is the expected one, the watch ends as unknown.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from fc_manager.inventory import Site
from fc_manager.redact import redact

IN_PROGRESS = ("Pending", "Running", "Undelivered")
JOB_DONE = ("Success", "Failure")
POLL_SECONDS = 2.0
OUTPUT_CHARS = 500
FIND_LIMIT_SECONDS = 120.0
RECOVERY_LIMIT_SECONDS = 600.0
RECOVER_PREFIX = "Recover Failed Site"
# The job types of a site update (site-update, and each site of bench-deploy).
UPDATE_JOB_TYPES = ("Update Site Migrate", "Update Site Pull")
RESTORED_STATUSES = ("Active", "Inactive")
NOT_RESTORED_STATUSES = ("Broken",)


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _status(value: Any) -> str:
    """FC shows an "Undelivered" job as "Pending" in its dashboard. So does fcm."""
    text = _str(value)
    return "Pending" if text == "Undelivered" else text


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
class JobState:
    """One look at one FC job of a site. `stage` is one of: finding (FC accepted the request; the
    new job is not visible yet), waiting (the job is queued), running, success, failure."""

    stage: str
    job: str = ""
    status: str = ""
    job_type: str = ""
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


def parse_job(data: Any) -> JobState:
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
    return JobState(
        stage=stage,
        job=_str(data.get("name")),
        status=status,
        job_type=_str(data.get("job_type")),
        steps=steps,
    )


# --- the shared watch -----------------------------------------------------------------


class JobReader(Protocol):
    """The three GET reads that the watch needs, for the team of the site."""

    def running_jobs(self, site: Site) -> list[JobRow]: ...

    def job(self, site: Site, name: str) -> JobState: ...

    def site_status(self, site: Site) -> str: ...


class SiteJobReader:
    """`JobReader` on an FC client. Every request goes to the team of the site."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def _call(self, site: Site, method: str, **params: Any) -> Any:
        return self.client.call(method, team=site.team.name, **params)

    def running_jobs(self, site: Site) -> list[JobRow]:
        return parse_running_jobs(self._call(site, "press.api.site.running_jobs", name=site.name))

    def job(self, site: Site, name: str) -> JobState:
        return parse_job(self._call(site, "press.api.site.job", job=name))

    def site_status(self, site: Site) -> str:
        data = self._call(site, "press.api.site.get", name=site.name)
        return _str(data.get("status")) if isinstance(data, dict) else ""


@dataclass(frozen=True)
class JobSpec:
    """What one action expects on the site.

    `expected`: the job types that decide the result. `find_limit`: seconds to wait for
    one of them. `recover`: after a failure, wait for FC to restore the site (D3)."""

    expected: tuple[str, ...]
    find_limit: float = FIND_LIMIT_SECONDS
    recover: bool = False


FINAL_STAGES = ("success", "failure", "recovered", "fatal", "unknown")


@dataclass(frozen=True)
class WatchState:
    """One look at the jobs of one site.

    `stage` is one of: finding (no expected job yet), waiting, running (the expected job),
    recovering (the expected job failed; FC restores the site), success, failure (with no
    recovery step, or no recovery seen in RECOVERY_LIMIT_SECONDS), recovered, fatal
    (FC could not restore the site), unknown (no expected job in the find limit).
    `jobs` holds every followed job, in the order the watch found them."""

    stage: str
    jobs: tuple[JobState, ...] = ()
    expected: JobState | None = None
    site_status: str = ""
    checked_at: float = field(default=0.0, compare=False)
    polls: int = field(default=0, compare=False)

    @property
    def final(self) -> bool:
        return self.stage in FINAL_STAGES

    @property
    def failed(self) -> bool:
        return self.stage in ("failure", "recovered", "fatal")

    @property
    def steps(self) -> tuple[JobStep, ...]:
        """The steps of every followed job. With more than one job, each step label starts
        with its job type, as in the FC Jobs tab."""
        many = len(self.jobs) > 1
        return tuple(
            replace(step, step=f"{job.job_type or job.job}: {step.step}") if many else step
            for job in self.jobs
            for step in job.steps
        )

    @property
    def failed_step(self) -> JobStep | None:
        return self.expected.failed_step if self.expected else None

    @property
    def current_step(self) -> JobStep | None:
        return self.expected.current_step if self.expected else None

    @property
    def outcome(self) -> str:
        """For a failed update: restored, not restored, or no recovery."""
        return {"recovered": "restored", "fatal": "not restored"}.get(
            self.stage, "no recovery" if self.stage == "failure" else ""
        )


class SiteJobWatch:
    """Find and follow the FC jobs of one site after an action.

    Each `poll()` reads the running jobs of the site once, adds every new job to the
    followed jobs, and reads each followed job that is not done with `site.job`. Only the
    first job of an expected type decides the result. An unrelated job that fails is
    shown, but it does not end the watch.

    FC lists only the Pending and Running jobs. A job that starts and ends between two
    polls is not seen (the short-job limit). When that job is the expected one, the watch
    ends as unknown after the find limit."""

    def __init__(
        self,
        reader: JobReader,
        site: Site,
        spec: JobSpec,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.reader = reader
        self.site = site
        self.spec = spec
        self.clock = clock
        self.started = clock()
        self.failed_at: float | None = None
        self.jobs: dict[str, JobState] = {}  # job name -> last look, in the found order
        self.state = WatchState(stage="finding")
        self.polls = 0

    def _expected_name(self) -> str:
        return next((n for n, j in self.jobs.items() if j.job_type in self.spec.expected), "")

    def _follow(self) -> None:
        for row in self.reader.running_jobs(self.site):
            if row.name not in self.jobs:
                self.jobs[row.name] = JobState(
                    stage="waiting", job=row.name, status=row.status, job_type=row.job_type
                )
        for name, last in list(self.jobs.items()):
            if last.status in JOB_DONE:
                continue
            look = self.reader.job(self.site, name)
            # site.job can leave the type out; the running row has it
            self.jobs[name] = replace(look, job=name, job_type=look.job_type or last.job_type)

    def _recovery(self) -> str:
        """recovered, fatal, or "" (no answer yet). First source that answers wins."""
        for job in self.jobs.values():
            if job.job_type.startswith(RECOVER_PREFIX) and job.status in JOB_DONE:
                return "recovered" if job.status == "Success" else "fatal"
        status = self.reader.site_status(self.site)
        self.state = replace(self.state, site_status=status)
        if status in RESTORED_STATUSES:
            return "recovered"
        if status in NOT_RESTORED_STATUSES:
            return "fatal"
        return ""

    def poll(self) -> WatchState:
        """One poll. Returns the new state; call again until `state.final`."""
        if self.state.final:
            return self.state
        self._follow()
        now = self.clock()
        name = self._expected_name()
        expected = self.jobs.get(name)
        stage, site_status = "finding", self.state.site_status
        if expected is None:
            if now - self.started >= self.spec.find_limit:
                stage, site_status = "unknown", self.reader.site_status(self.site)
        elif expected.status == "Success":
            stage, site_status = "success", self.reader.site_status(self.site)
        elif expected.status == "Failure":
            if not self.spec.recover:
                stage, site_status = "failure", self.reader.site_status(self.site)
            else:
                if self.failed_at is None:
                    self.failed_at = now
                stage = self._recovery() or "recovering"
                site_status = self.state.site_status
                if stage == "recovering" and now - self.failed_at >= RECOVERY_LIMIT_SECONDS:
                    stage = "failure"
        else:
            stage = expected.stage
        self.polls += 1
        self.state = WatchState(
            stage=stage,
            jobs=tuple(self.jobs.values()),
            expected=expected,
            site_status=site_status,
            checked_at=now,
            polls=self.polls,
        )
        return self.state

    def run(
        self, sleep: Callable[[float], None], poll_seconds: float = POLL_SECONDS
    ) -> Iterator[WatchState]:
        """Poll until the watch ends. Yield the state after every poll, also when nothing
        changed (for the liveness line)."""
        while True:
            state = self.poll()
            yield state
            if state.final:
                return
            sleep(poll_seconds)
