"""Update service tests (site-update group 3), on the fixture shapes."""

import copy
import json

import pytest
import respx

from fc_manager.api.client import FCClient
from fc_manager.errors import UpdateFailed, UpdateUnknown, UsageError
from fc_manager.inventory import Site, Team
from fc_manager.redact import Credentials
from fc_manager.update import NothingToUpdate, UpdatePlan, UpdateService, parse_update_info

from .conftest import fixture, method_url

TEAM = Team(name="team-acme", title="ACME", owner="owner@acme.example.com")
SITE = Site(TEAM, "erp.acme.example.com", "bench-1234", "ACME Prod", "Active", "16", "", True)


def service() -> UpdateService:
    return UpdateService(FCClient(Credentials("k-1234567", "s-1234567"), sleep=lambda _s: None))


FAILED_JOB = fixture("site_job_update_failed.json")["message"]  # live, 2026-11-17
TOO_MANY = 'mariadb-dump: Got error: 1040: "Too many connections" when trying to connect'


def job(name="job-21", job_type="Update Site Migrate", status="Running") -> dict:
    """A site.job answer. Failure: the live failed update job of 2026-11-17."""
    if status == "Failure":
        data = copy.deepcopy(FAILED_JOB)
        data["name"], data["job_type"] = name, job_type
        return data
    steps = [{"step_name": "Move Site", "status": status, "output": "", "duration": ""}]
    return {"name": name, "job_type": job_type, "status": status, "steps": steps}


def row(name="job-21", job_type="Update Site Migrate", status="Running") -> dict:
    """A press.api.site.running_jobs row: `id` is the job, `name` the job type."""
    return {"id": name, "name": job_type, "status": status}


# --- 3.1 parsers ----------------------------------------------------------------------


def test_parse_update_info_fixture_shape():
    info = parse_update_info(fixture("site_check_for_updates.json")["message"])
    assert info.update_available is True
    assert [a.app for a in info.apps] == ["frappe", "erpnext", "hrms"]
    assert [a.app for a in info.changes] == ["frappe", "hrms"]
    frappe, _, hrms = info.apps
    assert (frappe.current_version, frappe.next_version) == ("v16.1.0", "v16.2.0")
    assert frappe.branch_changes is False
    # No tag: the short hash.
    assert (hrms.current_version, hrms.next_version) == ("4444444", "5555555")
    assert hrms.branch_changes is True
    assert (hrms.current_branch, hrms.branch) == ("version-15", "version-16")


def test_parse_update_info_missing_fields():
    info = parse_update_info({"apps": [{"app": "x"}, {}, "bad", {"title": "no app"}]})
    assert info.update_available is False
    assert len(info.apps) == 1
    app = info.apps[0]
    assert (app.title, app.current_version, app.next_version) == ("x", "", "")
    assert app.update_available is False
    assert parse_update_info(None).apps == ()
    assert parse_update_info({"update_available": False}).changes == ()


def test_branch_change_without_flag_is_seen():
    info = parse_update_info(
        {"apps": [{"app": "a", "current_branch": "v15", "branch": "v16", "update_available": 1}]}
    )
    assert info.apps[0].branch_changes is True
    assert info.apps[0].update_available is True


# --- 3.2 check ------------------------------------------------------------------------


def mock_reads(router, status="Active", running=(), info=None):
    info = info if info is not None else fixture("site_check_for_updates.json")
    router.get(method_url("press.api.site.check_for_updates")).respond(json=info)
    router.get(method_url("press.api.site.get")).respond(json={"message": {"status": status}})
    router.get(method_url("press.api.site.running_jobs")).respond(json={"message": list(running)})


def test_check_no_update_raises_nothing_to_update():
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, info={"message": {"update_available": False}})
        with pytest.raises(NothingToUpdate):
            service().check(SITE)


@pytest.mark.parametrize("status", ["Active", "Inactive"])
def test_check_allowed_statuses(status):
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, status=status)
        plan = service().check(SITE, skip_failing_patches=True)
    assert plan.site == SITE
    assert plan.status == status
    assert [a.app for a in plan.apps] == ["frappe", "hrms"]
    assert plan.skip_failing_patches is True


@pytest.mark.parametrize("status", ["Broken", "Suspended", "Pending"])
def test_check_refuses_other_statuses(status):
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, status=status)
        with pytest.raises(UsageError) as info:
            service().check(SITE)
    assert info.value.exit_code == 2
    assert status in info.value.message


@pytest.mark.parametrize("job_status", ["Running", "Pending", "Undelivered"])
def test_check_refuses_job_in_progress(job_status):
    row = {"id": "job-5", "name": "Backup Site", "status": job_status, "steps": []}
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, running=[row])
        with pytest.raises(UsageError) as info:
            service().check(SITE)
    assert info.value.exit_code == 2
    assert "Backup Site" in info.value.message


# --- 3.3 start and watch --------------------------------------------------------------


PLAN = UpdatePlan(site=SITE, status="Active")


def test_start_sends_one_post_and_returns_record():
    with respx.mock() as router:
        route = router.post(method_url("press.api.site.update")).respond(
            json={"message": "su-0001"}
        )
        assert service().start(PLAN) == "su-0001"
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["X-Press-Team"] == "team-acme"
    assert json.loads(request.content) == {
        "name": "erp.acme.example.com",
        "skip_failing_patches": False,
        "skip_backups": False,
    }


@pytest.mark.parametrize("answer", [None, "", {"name": "su-1"}, 5])
def test_start_without_record_name_gives_empty_name(answer):
    with respx.mock() as router:
        route = router.post(method_url("press.api.site.update")).respond(json={"message": answer})
        assert service().start(PLAN) == ""
    assert route.call_count == 1


def test_start_returns_the_record_name():
    with respx.mock() as router:
        router.post(method_url("press.api.site.update")).respond(json={"message": " su-1 "})
        assert service().start(PLAN) == "su-1"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def run_watch(running, jobs, statuses=("Updating",), step=2.0):
    """Feed the watch. `running`: running_jobs answers (the last repeats). `jobs`: site.job
    answers per job name (the last repeats). `statuses`: site.get answers (the last
    repeats). Returns (states, error, routes)."""
    states, error = [], None
    clock = Clock()
    running = list(running)
    jobs = {k: list(v) for k, v in jobs.items()}
    statuses = list(statuses)

    def nxt(answers):
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def sleep(seconds):
        clock.now += step

    with respx.mock(assert_all_called=False) as router:
        routes = {
            "running": router.get(method_url("press.api.site.running_jobs")).mock(
                side_effect=lambda r: respx.MockResponse(json={"message": nxt(running)})
            ),
            "job": router.get(method_url("press.api.site.job")).mock(
                side_effect=lambda r: respx.MockResponse(
                    json={"message": nxt(jobs[r.url.params["job"]])}
                )
            ),
            "status": router.get(method_url("press.api.site.get")).mock(
                side_effect=lambda r: respx.MockResponse(
                    json={"message": {"status": nxt(statuses)}}
                )
            ),
            "record": router.get(method_url("press.api.client.get")),
        }
        try:
            for state in service().watch(PLAN, sleep=sleep, clock=clock):
                states.append(state)
        except (UpdateFailed, UpdateUnknown) as exc:
            error = exc
    return states, error, routes, clock


def test_watch_ends_on_success():
    states, error, routes, _ = run_watch(
        [[], [row(status="Pending")], [row()], []],
        {"job-21": [job(status="Pending"), job(), job(status="Success")]},
        statuses=("Active",),
    )
    assert error is None
    assert [s.stage for s in states] == ["finding", "waiting", "running", "success"]
    assert states[-1].site_status == "Active"
    assert [s.polls for s in states] == [1, 2, 3, 4]
    assert routes["status"].call_count == 1
    assert routes["record"].call_count == 0  # the Site Update record is not read


def test_watch_update_site_pull_is_an_update_job():
    states, error, _, _ = run_watch(
        [[row("job-3", "Update Site Pull")]],
        {"job-3": [job("job-3", "Update Site Pull", "Success")]},
        statuses=("Active",),
    )
    assert error is None
    assert states[-1].stage == "success"


def test_watch_failure_restored_by_the_recover_job():
    recover = "Recover Failed Site Update"
    states, error, _, _ = run_watch(
        [[row("job-20", "Backup Site"), row()], [row("job-22", recover)], []],
        {
            "job-20": [job("job-20", "Backup Site", "Success")],
            "job-21": [job(status="Failure")],
            "job-22": [job("job-22", recover, "Running"), job("job-22", recover, "Success")],
        },
    )
    assert [s.stage for s in states] == ["recovering", "recovering", "recovered"]
    assert [j.job_type for j in states[-1].jobs] == ["Backup Site", "Update Site Migrate", recover]
    assert isinstance(error, UpdateFailed)
    assert error.outcome == "recovered"
    assert error.step == "Backup Site Tables"
    assert error.server_message == TOO_MANY
    assert error.exit_code == 8
    assert "Update Site Migrate" in error.message
    assert "restored the site to the old bench" in error.message


def test_watch_failure_with_the_site_back_to_active():
    states, error, _, _ = run_watch(
        [[row()], []], {"job-21": [job(status="Failure")]}, statuses=("Updating", "Active")
    )
    assert error.outcome == "recovered"
    assert states[-1].site_status == "Active"


def test_watch_failure_with_the_site_broken():
    states, error, _, _ = run_watch(
        [[row()], []], {"job-21": [job(status="Failure")]}, statuses=("Broken",)
    )
    assert error.outcome == "fatal"
    assert error.step == "Backup Site Tables"
    assert "could not restore" in error.message
    assert "Broken" in error.hint
    assert "FC support" in error.hint
    assert states[-1].site_status == "Broken"


def test_watch_failure_with_no_recovery_in_ten_minutes():
    _, error, _, clock = run_watch([[row()], []], {"job-21": [job(status="Failure")]})
    assert error.outcome == "failure"
    assert error.step == "Backup Site Tables"
    assert error.exit_code == 8
    assert "no recovery in 10 minutes" in error.message
    assert "site-show erp.acme.example.com" in error.hint
    assert clock.now == pytest.approx(600)


def test_watch_no_update_job_in_two_minutes():
    states, error, _, clock = run_watch([[]], {})
    assert isinstance(error, UpdateUnknown)
    assert error.exit_code == 6
    assert "not known" in error.message
    assert "site-show erp.acme.example.com" in error.hint
    assert states[-1].stage == "unknown"
    assert clock.now == pytest.approx(120)
