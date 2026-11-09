"""Deploy service tests (bench-deploy group 3), on the real fixture shapes."""

import copy
import json

import httpx
import pytest
import respx

from fc_manager.api.client import FCClient
from fc_manager.deploy import (
    DeployService,
    parse_build,
    parse_deploy_info,
)
from fc_manager.errors import DeployFailed, UsageError
from fc_manager.inventory import Bench, Team
from fc_manager.redact import Credentials

from .conftest import fixture, method_url

TEAM = Team(name="team-acme", title="ACME", owner="owner@acme.example.com")
BENCH = Bench(TEAM, "bench-1234", "ACME Prod", "Version 16", "Active", 1, 10)


def info_data() -> dict:
    return copy.deepcopy(fixture("bench_deploy_information.json")["message"])


def build_data(status="Success", failed_at=None) -> dict:
    data = copy.deepcopy(fixture("deploy_candidate_build.json")["message"])
    data["status"] = status
    if failed_at is not None:
        for i, step in enumerate(data["build_steps"]):
            step["status"] = (
                "Success" if i < failed_at else "Failure" if i == failed_at else "Pending"
            )
        data["build_error"] = "pip install failed"
    return data


def service() -> DeployService:
    return DeployService(FCClient(Credentials("k-1234567", "s-1234567"), sleep=lambda _s: None))


# --- 3.1 parsers ----------------------------------------------------------------------


def test_parse_deploy_info_real_shape():
    info = parse_deploy_info(info_data(), BENCH)
    assert info.update_available is True
    assert [a.app for a in info.updates] == ["erpnext", "hrms", "name-27"]
    erp = next(a for a in info.apps if a.app == "erpnext")
    assert erp.current_version == erp.current_hash[:7]
    assert erp.next is not None and erp.next.name == "name-21"
    assert erp.next.version == "v16.54.0"  # from "Bumped to Version 16.54.0"; no tag
    assert "\n" not in erp.next.message
    frappe = next(a for a in info.apps if a.app == "frappe")
    assert frappe.has_update is False
    assert frappe.next_version == frappe.current_version
    assert [s.name for s in info.sites] == ["name-20.example.com"]
    assert info.last_build == "name-32"
    assert info.busy is False


def test_parse_deploy_info_missing_fields():
    info = parse_deploy_info({"apps": [{"app": "x"}], "sites": [{}], "last_deploy": None}, BENCH)
    assert info.apps[0].has_update is False
    assert info.apps[0].current_version == "not installed"
    assert info.sites == []
    assert info.last_build == ""
    assert info.nothing_to_deploy is True
    assert parse_deploy_info(None, BENCH).apps == []


def test_parse_build_real_shape():
    state = parse_build(build_data())
    assert state.stage == "finishing"
    assert state.steps[0].label == "Clone Repositories: Frappe Framework"
    assert state.steps[0].cached is True
    failed = parse_build(build_data("Failure", failed_at=3))
    assert failed.stage == "failure"
    assert failed.failed_step.label == failed.steps[3].label
    assert failed.message == "pip install failed"
    running = parse_build(
        {"status": "Running", "build_steps": [{"stage": "A", "status": "Running"}]}
    )
    assert running.stage == "building" and running.current_step.stage == "A"


def test_yanked_next_release_is_no_update():
    data = info_data()
    erp = next(a for a in data["apps"] if a["app"] == "erpnext")
    for release in erp["releases"]:
        if release["name"] == erp["next_release"]:
            release["is_yanked"] = 1
    info = parse_deploy_info(data, BENCH)
    assert "erpnext" not in [a.app for a in info.updates]


# --- 3.2 plan -------------------------------------------------------------------------


def test_plan_default_is_all_updates_and_bench_only():
    info = parse_deploy_info(info_data(), BENCH)
    plan = service().plan(info, apps=None, sites=[])
    assert [a.app for a in plan.apps] == ["erpnext", "hrms", "name-27"]
    assert plan.bench_only is True
    body = plan.payload()
    assert body["name"] == "bench-1234"
    assert body["sites"] == []
    assert body["run_will_fail_check"] is True
    erp = next(a for a in body["apps"] if a["app"] == "erpnext")
    assert set(erp) == {"app", "source", "release", "hash"}
    assert erp["release"] == "name-21"


def test_plan_with_site_sends_fc_row_with_safe_flags():
    data = info_data()
    data["sites"][0]["skip_backups"] = True  # FC row values never weaken the request
    info = parse_deploy_info(data, BENCH)
    plan = service().plan(info, apps=["hrms"], sites=["name-20.example.com"])
    body = plan.payload()
    assert [a["app"] for a in body["apps"]] == ["hrms"]
    assert body["sites"] == [
        {
            "name": "name-20.example.com",
            "server": "server-2.example.com",
            "bench": "bench-2",
            "skip_failing_patches": False,
            "skip_backups": False,
        }
    ]


def test_plan_unknown_app():
    info = parse_deploy_info(info_data(), BENCH)
    with pytest.raises(UsageError) as e:
        service().plan(info, apps=["frappe"], sites=[])
    assert "frappe" in e.value.message and "erpnext" in e.value.hint


def test_plan_unknown_site_lists_bench_sites():
    info = parse_deploy_info(info_data(), BENCH)
    with pytest.raises(UsageError) as e:
        service().plan(info, apps=None, sites=["other.example.com"])
    assert e.value.exit_code == 2
    assert "name-20.example.com" in e.value.hint


def test_plan_no_app_selected():
    info = parse_deploy_info(info_data(), BENCH)
    with pytest.raises(UsageError):
        service().plan(info, apps=[], sites=[])


def test_plan_only_removed_apps():
    data = info_data()
    for app in data["apps"]:
        app["update_available"] = None
    data["removed_apps"] = [{"app": "old_app"}]
    info = parse_deploy_info(data, BENCH)
    plan = service().plan(info, apps=[], sites=[])
    assert plan.apps == [] and plan.removed_apps == ["old_app"]
    assert plan.payload()["apps"] == []


# --- 3.3 service calls ----------------------------------------------------------------


def routes(router, statuses, builds=None, infos=None):
    """Mount deploy_status / client.get / deploy_information with response sequences."""
    status = router.get(method_url("press.api.bench.deploy_status"))
    status.side_effect = [httpx.Response(200, json={"message": s}) for s in statuses]
    build = router.get(method_url("press.api.client.get"))
    build.side_effect = [httpx.Response(200, json={"message": b}) for b in builds or []]
    info = router.get(method_url("press.api.bench.deploy_information"))
    info.side_effect = [httpx.Response(200, json={"message": i}) for i in infos or []]
    return status, build, info


def test_info_is_one_scoped_call():
    with respx.mock(assert_all_called=False) as router:
        route = router.get(method_url("press.api.bench.deploy_information")).respond(
            json={"message": info_data()}
        )
        service().info(BENCH)
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["X-Press-Team"] == "team-acme"
    assert request.url.params["name"] == "bench-1234"


def test_start_sends_one_post_with_plan_payload():
    plan = service().plan(parse_deploy_info(info_data(), BENCH), apps=["hrms"], sites=[])
    with respx.mock(assert_all_called=False) as router:
        route = router.post(method_url("press.api.bench.deploy_and_update")).respond(
            json={"message": "pipeline-9"}
        )
        assert service().start(plan) == "pipeline-9"
    assert route.call_count == 1
    assert json.loads(route.calls.last.request.content) == plan.payload()
    assert route.calls.last.request.headers["X-Press-Team"] == "team-acme"


def make_plan(sites=()):
    return service().plan(parse_deploy_info(info_data(), BENCH), apps=None, sites=list(sites))


def running(name="b-new"):
    data = build_data("Running")
    data["name"] = name
    data["build_steps"][0]["status"] = "Running"
    return data


def done(name="b-new"):
    data = build_data("Success")
    data["name"] = name
    return data


def idle_info(site_bench="bench-2", busy=False):
    data = info_data()
    data["has_running_release_pipeline"] = busy
    data["sites"][0]["bench"] = site_bench
    return data


def stages(states) -> list[str]:
    """Stages with repeats removed: the watch yields one state per FC answer."""
    out: list[str] = []
    for state in states:
        if not out or out[-1] != state.stage:
            out.append(state.stage)
    return out


def test_watch_new_flow_to_success_with_site_moved():
    plan = make_plan(sites=["name-20.example.com"])
    sleeps = []
    with respx.mock(assert_all_called=False) as router:
        status, build, info = routes(
            router,
            statuses=[
                {"is_validating": True, "candidate": None},
                {"is_deploy_in_progress": True, "candidate": "b-new"},
                {"is_deploy_in_progress": True, "candidate": "b-new"},
            ],
            builds=[running(), done(), done()],
            infos=[idle_info(busy=True), idle_info(site_bench="bench-3")],
        )
        states = list(service().watch(plan, sleep=sleeps.append))
    assert stages(states) == ["validating", "building", "finishing", "success"]
    assert states[-1].sites == (("name-20.example.com", True),)
    assert all(s >= 2.0 for s in sleeps)
    for route in (status, build, info):
        assert all(c.request.headers["X-Press-Team"] == "team-acme" for c in route.calls)
        assert all(c.request.method == "GET" for c in route.calls)


def test_watch_old_flow_finds_build_through_last_deploy():
    plan = make_plan()
    newer = idle_info()
    newer["last_deploy"] = {"name": "b-new", "status": "Running"}
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"candidate": None}, {"candidate": None}],
            builds=[running(), done(), done()],
            infos=[newer, newer, idle_info()],
        )
        states = list(service().watch(plan, sleep=lambda _s: None))
    assert stages(states) == ["building", "finishing", "success"]
    assert states[-1].sites == ()


def test_watch_build_failure_raises_with_step():
    plan = make_plan()
    failed = build_data("Failure", failed_at=2)
    failed["name"] = "b-new"
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"is_deploy_in_progress": True, "candidate": "b-new"}],
            builds=[failed],
        )
        gen = service().watch(plan, sleep=lambda _s: None)
        with pytest.raises(DeployFailed) as e:
            list(gen)
    assert e.value.exit_code == 8
    assert e.value.step == "Run Validations: Pre-build"
    assert e.value.server_message == "pip install failed"


def test_watch_gives_up_when_fc_ends_deploy_before_build():
    plan = make_plan()
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"candidate": None}] * 15,
            infos=[idle_info()] * 15,
        )
        with pytest.raises(DeployFailed) as e:
            list(service().watch(plan, sleep=lambda _s: None))
    assert "before a build started" in e.value.message


def test_state_for_bench_show():
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"is_deploy_in_progress": True, "candidate": "b-new"}],
            builds=[running()],
        )
        state = service().state(BENCH)
    assert state.stage == "building" and state.current_step is not None
    with respx.mock(assert_all_called=False) as router:
        routes(router, statuses=[{"is_validating": False, "candidate": None}])
        assert service().state(BENCH).stage == "idle"


def test_release_version_from_message_when_no_tag():
    from fc_manager.deploy import parse_release

    bumped = parse_release(
        {
            "name": "r1",
            "hash": "3d1284c0ffee",
            "tag": "",
            "message": "chore(release): Bumped to Version 16.55.2\n\nbody",
        }
    )
    assert bumped.version == "v16.55.2"
    tagged = parse_release(
        {
            "name": "r2",
            "hash": "3d1284c0ffee",
            "tag": "v16.55.3",
            "message": "Bumped to Version 16.55.2",
        }
    )
    assert tagged.version == "v16.55.3"


def test_release_version_falls_back_to_hash():
    from fc_manager.deploy import parse_release

    plain = parse_release(
        {"name": "r3", "hash": "495380bcafe", "message": "fix: version check in report"}
    )
    assert plain.version == "495380b"


def test_watch_yields_after_every_fc_answer():
    """A long step with no change still yields once per poll, with the answer time."""
    plan = make_plan()
    ticks = iter(range(100, 200, 2))
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"is_deploy_in_progress": True, "candidate": "b-new"}] * 4,
            builds=[running(), running(), running(), done(), done()],
            infos=[idle_info()],
        )
        states = list(service().watch(plan, sleep=lambda _s: None, clock=lambda: next(ticks)))
    assert [s.stage for s in states] == ["building"] * 3 + ["finishing", "success"]
    assert [s.polls for s in states] == [1, 2, 3, 4, 5]
    assert [s.checked_at for s in states][:4] == [100, 102, 104, 106]  # clock time of each answer
    assert states[0] == states[1]  # liveness fields do not count as a change


def test_watch_idle_polls_show_starting():
    plan = make_plan()
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"candidate": None}]
            + [{"is_deploy_in_progress": True, "candidate": "b-new"}] * 2,
            builds=[running(), done(), done()],
            infos=[idle_info(), idle_info()],
        )
        states = list(service().watch(plan, sleep=lambda _s: None))
    assert stages(states) == ["starting", "building", "finishing", "success"]


def test_watch_waits_for_site_move_after_bench_ready():
    plan = make_plan(sites=["name-20.example.com"])
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"is_deploy_in_progress": True, "candidate": "b-new"}] * 2,
            builds=[done(), done()],
            infos=[idle_info(), idle_info(), idle_info(site_bench="bench-3")],
        )
        states = list(service().watch(plan, sleep=lambda _s: None))
    assert stages(states) == ["finishing", "updating_sites", "success"]
    waiting = next(s for s in states if s.stage == "updating_sites")
    assert waiting.sites == (("name-20.example.com", False),)
    assert states[-1].sites == (("name-20.example.com", True),)


def test_watch_site_not_confirmed_in_time():
    from fc_manager.errors import SiteUpdateUnknown

    plan = make_plan(sites=["name-20.example.com"])
    ticks = iter(range(0, 10_000, 600))  # 10 minutes per clock read
    with respx.mock(assert_all_called=False) as router:
        routes(
            router,
            statuses=[{"is_deploy_in_progress": True, "candidate": "b-new"}],
            builds=[done(), done()],
            infos=[idle_info()] * 20,
        )
        with pytest.raises(SiteUpdateUnknown) as e:
            list(service().watch(plan, sleep=lambda _s: None, clock=lambda: next(ticks)))
    assert e.value.exit_code == 6
    assert "name-20.example.com" in e.value.message and "not known" in e.value.message
