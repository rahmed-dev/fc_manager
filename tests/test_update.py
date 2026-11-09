"""Update service tests (site-update group 3), on the fixture shapes."""

import copy
import json

import pytest
import respx

from fc_manager import update as update_module
from fc_manager.api.client import FCClient
from fc_manager.errors import UpdateFailed, UpdateUnknown, UsageError
from fc_manager.inventory import Site, Team
from fc_manager.redact import Credentials
from fc_manager.update import (
    NothingToUpdate,
    UpdatePlan,
    UpdateService,
    parse_update_info,
    parse_update_record,
)

from .conftest import fixture, method_url

TEAM = Team(name="team-acme", title="ACME", owner="owner@acme.example.com")
SITE = Site(TEAM, "erp.acme.example.com", "bench-1234", "ACME Prod", "Active", "16", "", True)


def service() -> UpdateService:
    return UpdateService(FCClient(Credentials("k-1234567", "s-1234567"), sleep=lambda _s: None))


def record(status="Running", steps=None, recover_job=None, name="su-0001") -> dict:
    data = copy.deepcopy(fixture("site_update.json")["message"])
    data["name"] = name
    data["status"] = status
    data["recover_job"] = recover_job
    if steps is not None:
        for step, step_status in zip(data["steps"], steps, strict=True):
            step["status"] = step_status
    return data


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


def test_parse_update_record_fixture_shape():
    state = parse_update_record(fixture("site_update.json")["message"])
    assert state.stage == "running"
    assert state.record == "su-0001"
    assert state.destination_bench == "bench-2"
    assert state.current_step.label == "Move Site"
    assert [s.label for s in state.steps][:2] == ["Deactivate Site", "Backup Site"]
    assert state.final is False


@pytest.mark.parametrize(
    "status,stage,final",
    [
        ("Pending", "waiting", False),
        ("Scheduled", "waiting", False),
        ("Running", "running", False),
        ("Failure", "failure", False),
        ("Recovering", "recovering", False),
        ("Success", "success", True),
        ("Recovered", "recovered", True),
        ("Fatal", "fatal", True),
        ("Cancelled", "cancelled", True),
        (None, "running", False),
    ],
)
def test_parse_update_record_stages(status, stage, final):
    state = parse_update_record({"status": status})
    assert (state.stage, state.final) == (stage, final)


def test_parse_update_record_missing_fields():
    state = parse_update_record({"steps": [{}, "x", {"stage": "Update Site"}]})
    assert [s.label for s in state.steps] == ["", "Update Site"]
    assert parse_update_record(None).steps == ()


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
def test_start_without_record_name_is_unknown(answer):
    with respx.mock() as router:
        route = router.post(method_url("press.api.site.update")).respond(json={"message": answer})
        with pytest.raises(UpdateUnknown) as info:
            service().start(PLAN)
    assert route.call_count == 1
    assert info.value.exit_code == 6
    assert info.value.hint == "Run: fcm site-show erp.acme.example.com"


def run_watch(records, site_status="Active", clock=None):
    """Feed `records` to the watch. Returns (states, error, route of client.get)."""
    states, error = [], None
    with respx.mock(assert_all_called=False) as router:
        get = router.get(method_url("press.api.client.get"))
        get.side_effect = [respx.MockResponse(json={"message": r}) for r in records]
        status = router.get(method_url("press.api.site.get")).respond(
            json={"message": {"status": site_status}}
        )
        try:
            kwargs = {"clock": clock} if clock else {}
            for state in service().watch(PLAN, "su-0001", sleep=lambda _s: None, **kwargs):
                states.append(state)
        except UpdateFailed as exc:
            error = exc
        return states, error, get, status


def test_watch_ends_on_success_with_new_bench():
    states, error, get, status = run_watch(
        [record("Pending"), record("Running"), record("Success")]
    )
    assert error is None
    assert [s.stage for s in states] == ["waiting", "running", "success"]
    assert states[-1].destination_bench == "bench-2"
    assert states[-1].site_status == "Active"
    assert [s.polls for s in states] == [1, 2, 3]
    assert get.calls.last.request.url.params["doctype"] == "Site Update"
    assert get.calls.last.request.url.params["name"] == "su-0001"
    assert status.call_count == 1


def test_watch_keeps_polling_through_failure_and_recovering():
    failed = ("Success", "Success", "Failure", "Pending", "Pending")
    states, error, _, status = run_watch(
        [
            record("Running"),
            record("Failure", failed),
            record("Recovering", failed, recover_job="job-12"),
            record("Recovered", failed, recover_job="job-12"),
        ]
    )
    assert [s.stage for s in states] == ["running", "failure", "recovering", "recovered"]
    assert isinstance(error, UpdateFailed)
    assert error.outcome == "recovered"
    assert error.step == "Move Site"
    assert error.exit_code == 8
    assert "restored the site to the old bench" in error.message
    assert status.call_count == 1


def test_watch_fatal():
    failed = ("Success", "Success", "Success", "Failure", "Pending")
    states, error, _, _ = run_watch([record("Fatal", failed)], site_status="Broken")
    assert error.outcome == "fatal"
    assert error.step == "Migrate Site"
    assert "could not restore" in error.message
    assert "Broken" in error.hint
    assert "FC support" in error.hint
    assert states[-1].site_status == "Broken"


def test_watch_cancelled():
    _, error, _, _ = run_watch([record("Cancelled")])
    assert error.outcome == "cancelled"
    assert "cancelled on FC" in error.message


def test_watch_failure_without_recovery_past_limit(monkeypatch):
    monkeypatch.setattr(update_module, "FAILURE_LIMIT_SECONDS", 0.0)
    failed = ("Success", "Success", "Failure", "Pending", "Pending")
    states, error, _, status = run_watch([record("Failure", failed)])
    assert error.outcome == "failure"
    assert error.step == "Move Site"
    assert error.exit_code == 8
    assert "site-show erp.acme.example.com" in error.hint
    assert status.call_count == 1
    assert len(states) == 1


def test_watch_failure_resets_when_recovery_starts():
    ticks = iter(range(0, 10_000, 400))
    failed = ("Success", "Success", "Failure", "Pending", "Pending")
    states, error, _, _ = run_watch(
        [
            record("Failure", failed),
            record("Failure", failed, recover_job="job-12"),
            record("Recovering", failed, recover_job="job-12"),
            record("Recovered", failed, recover_job="job-12"),
        ],
        clock=lambda: next(ticks),
    )
    assert error.outcome == "recovered"
