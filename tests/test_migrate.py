"""Migrate service tests (site-migrate group 3), on the fixture shapes."""

import copy
import json

import pytest
import respx

from fc_manager import migrate as migrate_module
from fc_manager.api.client import FCClient
from fc_manager.errors import MigrateFailed, MigrateUnknown, UsageError
from fc_manager.inventory import Site, Team
from fc_manager.migrate import MigratePlan, MigrateService, parse_job, parse_running_jobs
from fc_manager.redact import Credentials

from .conftest import fixture, method_url

TEAM = Team(name="team-acme", title="ACME", owner="owner@acme.example.com")
SITE = Site(TEAM, "erp.acme.example.com", "bench-1234", "ACME Prod", "Active", "16", "", False)


def service() -> MigrateService:
    return MigrateService(FCClient(Credentials("k-1234567", "s-1234567"), sleep=lambda _s: None))


def job_data(status="Running", steps=("Success", "Running", "Pending"), name="job-4") -> dict:
    data = copy.deepcopy(fixture("site_job.json")["message"])
    data["name"] = name
    data["status"] = status
    for step, step_status in zip(data["steps"], steps, strict=True):
        step["status"] = step_status
    return data


def running_row(name, job_type="Migrate Site", status="Pending") -> dict:
    """A press.api.site.running_jobs row: `id` is the job, `name` the job type."""
    return {"id": name, "name": job_type, "status": status, "steps": []}


# --- 3.1 parsers ----------------------------------------------------------------------


def test_parse_running_jobs_fixture_shape():
    rows = parse_running_jobs(fixture("site_running_jobs.json")["message"])
    assert [(r.name, r.job_type, r.status) for r in rows] == [("job-5", "Backup Site", "Running")]


def test_parse_running_jobs_missing_fields_and_undelivered():
    rows = parse_running_jobs([{"id": "j", "status": "Undelivered"}, {"name": "x"}, None])
    assert [(r.name, r.job_type, r.status) for r in rows] == [("j", "", "Pending")]
    assert parse_running_jobs(None) == []


def test_parse_job_fixture_shape():
    state = parse_job(fixture("site_job.json")["message"])
    assert state.stage == "running"
    assert state.job == "job-4"
    assert [s.label for s in state.steps] == ["Backup Site", "Migrate Site", "Activate Site"]
    assert state.current_step.label == "Migrate Site"
    assert state.final is False


@pytest.mark.parametrize(
    "status,stage",
    [("Success", "success"), ("Failure", "failure"), ("Undelivered", "waiting"), (None, "running")],
)
def test_parse_job_stages(status, stage):
    assert parse_job({"status": status}).stage == stage


def test_parse_job_missing_fields():
    state = parse_job({"steps": [{}, "x"]})
    assert state.steps[0].label == ""
    assert parse_job(None).steps == ()


# --- 3.2 check ------------------------------------------------------------------------


def mock_reads(router, status="Active", running=()):
    router.get(method_url("press.api.site.get")).respond(json={"message": {"status": status}})
    return router.get(method_url("press.api.site.running_jobs")).respond(
        json={"message": list(running)}
    )


@pytest.mark.parametrize("status", ["Active", "Inactive", "Broken"])
def test_check_passes_for_allowed_status(status):
    with respx.mock(assert_all_called=False) as router:
        running = mock_reads(router, status=status)
        plan = service().check(SITE, skip_failing_patches=True)
    assert plan == MigratePlan(SITE, status, True)
    request = running.calls.last.request
    assert request.headers["X-Press-Team"] == "team-acme"
    assert request.url.params["name"] == "erp.acme.example.com"


@pytest.mark.parametrize("status", ["Suspended", "Pending", "Archived", ""])
def test_check_refuses_other_status(status):
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, status=status)
        with pytest.raises(UsageError) as info:
            service().check(SITE)
    assert (status or "unknown") in info.value.message
    assert info.value.exit_code == 2


@pytest.mark.parametrize("job_status", ["Running", "Pending", "Undelivered"])
def test_check_refuses_a_job_in_progress(job_status):
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, running=[running_row("j-9", "Backup Site", job_status)])
        with pytest.raises(UsageError) as info:
            service().check(SITE)
    assert "Backup Site" in info.value.message
    assert info.value.exit_code == 2


# --- 3.3 start and watch --------------------------------------------------------------


def test_start_sends_one_post():
    with respx.mock() as router:
        route = router.post(method_url("press.api.site.migrate")).respond(json={"message": None})
        service().start(MigratePlan(SITE, "Active", True))
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Press-Team"] == "team-acme"
    assert json.loads(route.calls.last.request.content) == {
        "name": "erp.acme.example.com",
        "skip_failing_patches": True,
    }


def run_watch(router, running_seq, job_seq, final_status="Active"):
    """running_seq: running_jobs rows per find poll. job_seq: job docs per follow poll."""
    running_iter = iter(running_seq)
    job_iter = iter(job_seq)
    router.get(method_url("press.api.site.running_jobs")).mock(
        side_effect=lambda r: respx.MockResponse(json={"message": next(running_iter)})
    )
    router.get(method_url("press.api.site.job")).mock(
        side_effect=lambda r: respx.MockResponse(json={"message": next(job_iter)})
    )
    site_get = router.get(method_url("press.api.site.get")).respond(
        json={"message": {"status": final_status}}
    )
    sleeps = []
    states = []
    plan = MigratePlan(SITE, "Active", False)
    for state in service().watch(plan, sleep=sleeps.append, poll_seconds=2.0):
        states.append(state)
    return states, sleeps, site_get


def test_watch_finds_the_migrate_job_and_ends_on_success():
    with respx.mock(assert_all_called=False) as router:
        states, sleeps, site_get = run_watch(
            router,
            running_seq=[
                [],
                [running_row("j-1", "Backup Site", "Running")],
                [running_row("job-4")],
            ],
            job_seq=[
                job_data("Pending", ("Pending", "Pending", "Pending")),
                job_data("Running"),
                job_data("Success", ("Success", "Success", "Success")),
            ],
        )
    assert [s.stage for s in states] == ["finding", "finding", "waiting", "running", "success"]
    assert [s.polls for s in states] == [1, 2, 3, 4, 5]
    assert all(s.checked_at > 0 for s in states)
    assert states[-1].site_status == "Active"
    assert states[-1].job == "job-4"
    assert site_get.call_count == 1
    assert sleeps and all(s == 2.0 for s in sleeps)


def test_watch_failure_names_the_step():
    with respx.mock(assert_all_called=False) as router, pytest.raises(MigrateFailed) as info:
        run_watch(
            router,
            running_seq=[[running_row("job-4", status="Running")]],
            job_seq=[job_data("Failure", ("Success", "Failure", "Pending"))],
            final_status="Broken",
        )
    assert info.value.step == "Migrate Site"
    assert info.value.exit_code == 8
    assert "Broken" in info.value.hint
    assert "fcm site-show erp.acme.example.com" in info.value.hint


def test_watch_job_not_found(monkeypatch):
    monkeypatch.setattr(migrate_module, "FIND_LIMIT_SECONDS", 0)
    with respx.mock(assert_all_called=False) as router, pytest.raises(MigrateUnknown) as info:
        run_watch(router, running_seq=[[]] * 3, job_seq=[], final_status="Pending")
    assert info.value.exit_code == 6
    assert "not known" in info.value.message
    assert info.value.hint == (
        "Site status on FC: Pending. Run: fcm site-show erp.acme.example.com"
    )
