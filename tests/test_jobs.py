"""Shared site job watch (site-job-finder groups 2): find every job, decide on the expected
job, and the recovery outcome after a failed update."""

import pytest

from fc_manager import jobs
from fc_manager.inventory import Site, Team
from fc_manager.jobs import JobRow, JobSpec, JobState, JobStep, SiteJobWatch, parse_job

TEAM = Team(name="team-acme", title="ACME", owner="owner@acme.example.com")
SITE = Site(TEAM, "erp.acme.example.com", "bench-1234", "ACME Prod", "Updating", "16", "", False)
UPDATE = JobSpec(expected=("Update Site Migrate", "Update Site Pull"), recover=True)
MIGRATE = JobSpec(expected=("Migrate Site",))
TOO_MANY = 'mariadb-dump: Got error: 1040: "Too many connections" when trying to connect'


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeReader:
    """Scripted FC: `running` is a list of running_jobs answers (the last one repeats);
    `looks` maps a job name to its site.job answers (the last one repeats); `statuses` is
    the site status answers (the last one repeats)."""

    def __init__(self, running, looks, statuses=("Updating",)):
        self.running = list(running)
        self.looks = {k: list(v) for k, v in looks.items()}
        self.statuses = list(statuses)
        self.job_reads = []

    @staticmethod
    def _next(answers):
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def running_jobs(self, site):
        return self._next(self.running)

    def job(self, site, name):
        self.job_reads.append(name)
        return self._next(self.looks[name])

    def site_status(self, site):
        return self._next(self.statuses)


def row(name, job_type, status="Running"):
    return JobRow(name=name, job_type=job_type, status=status)


def look(name, job_type, status, steps=()):
    stage = {"Success": "success", "Failure": "failure", "Pending": "waiting"}.get(
        status, "running"
    )
    return JobState(stage=stage, job=name, status=status, job_type=job_type, steps=steps)


FAILED_STEPS = (
    JobStep("Clear Backup Directory", "Success", "0.1"),
    JobStep("Backup Site Tables", "Failure", "38.0", TOO_MANY),
    JobStep("Move Site", "Skipped", ""),
)


def run(watch, clock, step=2.0, limit=2000):
    states = []
    for _ in range(limit):
        state = watch.poll()
        states.append(state)
        if state.final:
            return states
        clock.now += step
    raise AssertionError("the watch did not end")


# --- 2.2 find and follow ---------------------------------------------------------------


def test_parse_job_live_failure_shape():
    data = {
        "name": "job-21",
        "job_type": "Update Site Migrate",
        "status": "Failure",
        "steps": [
            {"step_name": "Backup Site Tables", "status": "Failure", "output": TOO_MANY},
            {"step_name": "Move Site", "status": "Skipped", "output": None},
        ],
    }
    state = parse_job(data)
    assert state.job_type == "Update Site Migrate"
    assert state.stage == "failure"
    assert state.failed_step.label == "Backup Site Tables"
    assert state.failed_step.output == TOO_MANY


def test_expected_job_success():
    clock = Clock()
    reader = FakeReader(
        [[row("j1", "Migrate Site", "Pending")], [row("j1", "Migrate Site")], []],
        {"j1": [look("j1", "Migrate Site", "Running"), look("j1", "Migrate Site", "Success")]},
        statuses=("Active",),
    )
    states = run(SiteJobWatch(reader, SITE, MIGRATE, clock), clock)
    assert [s.stage for s in states] == ["running", "success"]
    assert states[-1].site_status == "Active"
    assert [s.polls for s in states] == [1, 2]


def test_expected_job_failure_names_step_and_output():
    clock = Clock()
    reader = FakeReader(
        [[row("j1", "Migrate Site")], []],
        {"j1": [look("j1", "Migrate Site", "Failure", FAILED_STEPS)]},
        statuses=("Broken",),
    )
    state = run(SiteJobWatch(reader, SITE, MIGRATE, clock), clock)[-1]
    assert state.stage == "failure"
    assert state.expected.job_type == "Migrate Site"
    assert state.failed_step.label == "Backup Site Tables"
    assert state.failed_step.output == TOO_MANY


def test_other_jobs_are_followed_and_an_unrelated_failure_does_not_end_the_watch():
    clock = Clock()
    reader = FakeReader(
        [
            [row("b1", "Backup Site"), row("c1", "Update Site Configuration")],
            [row("u1", "Update Site Migrate")],
            [],
        ],
        {
            "b1": [look("b1", "Backup Site", "Success")],
            "c1": [look("c1", "Update Site Configuration", "Failure")],
            "u1": [look("u1", "Update Site Migrate", "Running"), look("u1", "", "Success")],
        },
    )
    states = run(SiteJobWatch(reader, SITE, UPDATE, clock), clock)
    assert [s.stage for s in states] == ["finding", "running", "success"]
    final = states[-1]
    assert [(j.job_type, j.status) for j in final.jobs] == [
        ("Backup Site", "Success"),
        ("Update Site Configuration", "Failure"),
        ("Update Site Migrate", "Success"),  # type kept from the running row
    ]
    assert reader.job_reads.count("b1") == 1  # a done job is not read again


def test_no_expected_job_within_the_find_limit():
    clock = Clock()
    reader = FakeReader(
        [[row("b1", "Backup Site")], []], {"b1": [look("b1", "Backup Site", "Success")]}
    )
    states = run(SiteJobWatch(reader, SITE, MIGRATE, clock), clock)
    assert states[-1].stage == "unknown"
    assert states[-1].site_status == "Updating"
    assert clock.now == pytest.approx(jobs.FIND_LIMIT_SECONDS)


def test_find_limit_of_the_action():
    clock = Clock()
    spec = JobSpec(expected=("Update Site Migrate",), find_limit=30 * 60, recover=True)
    states = run(SiteJobWatch(FakeReader([[]], {}), SITE, spec, clock), clock)
    assert states[-1].stage == "unknown"
    assert clock.now == pytest.approx(30 * 60)


# --- 2.3 recovery ----------------------------------------------------------------------


def failed_update(running_after, extra_looks=None, statuses=("Updating",)):
    looks = {"u1": [look("u1", "Update Site Migrate", "Failure", FAILED_STEPS)]}
    looks.update(extra_looks or {})
    return FakeReader([[row("u1", "Update Site Migrate")], *running_after], looks, statuses)


def test_recover_job_success_gives_recovered():
    clock = Clock()
    reader = failed_update(
        [[row("r1", "Recover Failed Site Update")], []],
        {"r1": [look("r1", "Recover Failed Site Update", "Running"),
                look("r1", "Recover Failed Site Update", "Success")]},
    )  # fmt: skip
    states = run(SiteJobWatch(reader, SITE, UPDATE, clock), clock)
    assert [s.stage for s in states] == ["recovering", "recovering", "recovered"]
    assert states[-1].outcome == "restored"
    assert states[-1].failed_step.label == "Backup Site Tables"


def test_recover_job_failure_gives_fatal():
    clock = Clock()
    reader = failed_update(
        [[row("r1", "Recover Failed Site Update")]],
        {"r1": [look("r1", "Recover Failed Site Update", "Failure")]},
    )
    state = run(SiteJobWatch(reader, SITE, UPDATE, clock), clock)[-1]
    assert state.stage == "fatal"
    assert state.outcome == "not restored"


def test_missed_recover_job_with_site_active_gives_recovered():
    clock = Clock()
    reader = failed_update([[]], statuses=("Updating", "Active"))
    state = run(SiteJobWatch(reader, SITE, UPDATE, clock), clock)[-1]
    assert state.stage == "recovered"
    assert state.site_status == "Active"


def test_site_broken_gives_fatal():
    clock = Clock()
    reader = failed_update([[]], statuses=("Broken",))
    state = run(SiteJobWatch(reader, SITE, UPDATE, clock), clock)[-1]
    assert state.stage == "fatal"
    assert state.site_status == "Broken"


def test_no_recovery_in_ten_minutes_gives_failure():
    clock = Clock()
    reader = failed_update([[]], statuses=("Updating",))
    states = run(SiteJobWatch(reader, SITE, UPDATE, clock), clock)
    assert states[-1].stage == "failure"
    assert states[-1].outcome == "no recovery"
    assert clock.now == pytest.approx(jobs.RECOVERY_LIMIT_SECONDS)


def test_run_yields_until_final_and_sleeps_between_polls():
    clock = Clock()
    reader = FakeReader(
        [[row("j1", "Migrate Site")]],
        {"j1": [look("j1", "Migrate Site", "Running"), look("j1", "Migrate Site", "Success")]},
    )
    sleeps = []
    states = list(SiteJobWatch(reader, SITE, MIGRATE, clock).run(sleeps.append))
    assert [s.stage for s in states] == ["running", "success"]
    assert sleeps == [jobs.POLL_SECONDS]


def test_parse_job_live_recover_shape():
    from .conftest import fixture

    state = parse_job(fixture("site_job_recover.json")["message"])
    assert state.job_type.startswith(jobs.RECOVER_PREFIX)
    assert state.status == "Success"
    assert [s.label for s in state.steps] == ["Disable Maintenance Mode"]


def test_parse_job_live_failure_fixture():
    from .conftest import fixture

    state = parse_job(fixture("site_job_update_failed.json")["message"])
    assert state.job_type in jobs.UPDATE_JOB_TYPES
    assert state.failed_step.label == "Backup Site Tables"
    assert "Too many connections" in state.failed_step.output
    assert {s.status for s in state.steps} == {"Success", "Failure", "Skipped"}
