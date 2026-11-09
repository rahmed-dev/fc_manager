"""bench-deploy group 5: `fcm bench-show` and `fcm bench-deploy`."""

import copy
import json

import pytest

from fc_manager.cli import deploy as deploy_cli
from fc_manager.cli import picker

from .conftest import fixture, save_profile

SITE = "name-20.example.com"


def info(**changes) -> dict:
    data = copy.deepcopy(fixture("bench_deploy_information.json")["message"])
    data.update(changes)
    return data


def build(status="Success", name="b-new", failed_at=None) -> dict:
    data = copy.deepcopy(fixture("deploy_candidate_build.json")["message"])
    data.update(status=status, name=name)
    if status == "Running":
        data["build_steps"][0]["status"] = "Running"
    if failed_at is not None:
        for i, step in enumerate(data["build_steps"]):
            step["status"] = (
                "Success" if i < failed_at else "Failure" if i == failed_at else "Pending"
            )
        data["build_error"] = "pip install failed"
    return data


@pytest.fixture
def dfc(env, fc, monkeypatch):
    """Fake FC with bench-1234 (team-acme) ready to deploy, and no real sleeping."""
    save_profile()
    fc.deploy_infos["bench-1234"] = [info()]
    fc.statuses = [
        {"is_validating": True, "candidate": None},
        {"is_deploy_in_progress": True, "candidate": "b-new"},
    ]
    fc.builds = [build("Running"), build("Success")]
    monkeypatch.setattr(deploy_cli.time, "sleep", lambda _s: None)
    return fc


def after_bench_pick(fc):
    first = next(i for i, c in enumerate(fc.teams_seen) if c[0].endswith("deploy_information"))
    return fc.teams_seen[first:]


def finish_infos(fc, site_bench="bench-2"):
    """After the build: one busy look, then idle with the site on `site_bench`."""
    done = info(has_running_release_pipeline=False)
    done["sites"][0]["bench"] = site_bench
    fc.deploy_infos["bench-1234"] = [info(), info(has_running_release_pipeline=True), done]


# --- 5.1 bench show -------------------------------------------------------------------


def test_bench_show_table(dfc, cli):
    result = cli("bench-show", "bench-1234")
    assert result.code == 0, result.err
    assert "erpnext" in result.out and "Update" in result.out
    assert SITE in result.out
    assert "no deploy running" in result.out
    assert dfc.posts == []
    assert all(m != "POST" for _, _, m in dfc.teams_seen)


def test_bench_show_json(dfc, cli):
    result = cli("bench-show", "ACME Prod", "--json")
    assert result.code == 0, result.err
    data = json.loads(result.out)
    assert data["bench"]["name"] == "bench-1234"
    assert {"app", "current", "next", "update_available"} <= set(data["apps"][0])
    assert data["sites"] == [{"name": SITE, "server": "server-2.example.com"}]
    assert data["deploy"]["stage"] == "idle"


def test_bench_show_running_deploy(dfc, cli):
    dfc.deploy_infos["bench-1234"] = [info(deploy_in_progress=True)]
    dfc.statuses = [{"is_deploy_in_progress": True, "candidate": "b-new"}]
    dfc.builds = [build("Running")]
    result = cli("bench-show", "bench-1234")
    assert result.code == 0, result.err
    assert "building the new bench image" in result.out
    assert "now: Clone Repositories: Frappe Framework" in result.out


def test_bench_show_needs_bench_in_script(dfc, cli):
    assert cli("bench-show", "--json").code == 2


# --- 5.2 / 5.4 walk without a terminal ------------------------------------------------


def test_deploy_needs_confirm(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--json")
    assert result.code == 2
    assert "--confirm bench-1234" in json.loads(result.err)["error"]
    assert dfc.posts == []


def test_deploy_wrong_confirm(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-9999")
    assert result.code == 2
    assert dfc.posts == []


def test_deploy_title_is_not_a_confirm_in_scripts(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "ACME Prod")
    assert result.code == 2
    assert dfc.posts == []


def test_deploy_needs_app_option(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--confirm", "bench-1234")
    assert result.code == 2
    assert "--all-apps" in result.err
    assert dfc.posts == []


def test_deploy_unknown_site(dfc, cli):
    result = cli(
        "bench-deploy", "bench-1234", "--all-apps", "--site", "other.example.com",
        "--confirm", "bench-1234",
    )  # fmt: skip
    assert result.code == 2
    assert SITE in result.err
    assert dfc.posts == []


def test_deploy_unknown_app(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--app", "frappe", "--confirm", "bench-1234")
    assert result.code == 2
    assert "erpnext" in result.err
    assert dfc.posts == []


def test_dry_run_json(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--dry-run", "--json")
    assert result.code == 0, result.err
    data = json.loads(result.out)
    assert data["dry_run"] is True
    plan = data["plan"]
    assert plan["bench"]["name"] == "bench-1234"
    assert plan["team"]["owner"] == "acme@example.com"
    assert plan["bench_only"] is True
    assert [a["app"] for a in plan["apps"]] == ["erpnext", "hrms", "name-27"]
    assert dfc.posts == []


def test_dry_run_table_preview(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--app", "hrms", "--site", SITE, "--dry-run")
    assert result.code == 0, result.err
    for text in ("Deploy preview", "Profile", "work", "acme@example.com", "ACME Prod (bench-1234)"):
        assert text in result.out
    assert SITE in result.out and "backup" in result.out
    assert "Dry run: nothing was sent to FC." in result.out
    assert dfc.posts == []


def test_nothing_to_deploy(dfc, cli):
    data = info(update_available=False)
    for app in data["apps"]:
        app["update_available"] = None
    dfc.deploy_infos["bench-1234"] = [data]
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234")
    assert result.code == 0
    assert "up to date" in result.out
    assert dfc.posts == []


def test_deploy_already_running(dfc, cli):
    dfc.deploy_infos["bench-1234"] = [info(deploy_in_progress=True)]
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234")
    assert result.code == 2
    assert "fcm bench-show bench-1234" in result.err
    assert dfc.posts == []


def test_deploy_permission_names_owner(dfc, cli):
    del dfc.deploy_infos["bench-1234"]
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234")
    assert result.code == 4
    assert "acme@example.com" in result.err
    assert dfc.posts == []


# --- 5.5 deploy, progress and result --------------------------------------------------


def test_full_deploy_json_bench_only(dfc, cli):
    finish_infos(dfc)
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234", "--json")
    assert result.code == 0, result.err
    events = [json.loads(line) for line in result.out.splitlines()]
    assert events[0]["event"] == "accepted" and events[0]["ref"] == "pipeline-1"
    stages = [e["stage"] for e in events if e["event"] == "progress"]
    assert stages == ["validating", "building", "finishing", "success"]
    assert events[-1]["event"] == "result"
    assert len(dfc.posts) == 1
    body = dfc.posts[0]
    assert body["name"] == "bench-1234" and body["sites"] == []
    assert body["run_will_fail_check"] is True
    assert {a["app"] for a in body["apps"]} == {"erpnext", "hrms", "name-27"}
    # Scoped: every request after the bench pick goes to the bench team only.
    assert {team for _, team, _ in after_bench_pick(dfc)} == {"team-acme"}


def test_deploy_with_site_moved(dfc, cli):
    finish_infos(dfc, site_bench="bench-3")
    result = cli(
        "bench-deploy", "bench-1234", "--app", "hrms", "--site", SITE,
        "--confirm", "bench-1234",
    )  # fmt: skip
    assert result.code == 0, result.err
    assert f"{SITE} (updated)" in result.out
    sent = dfc.posts[0]["sites"][0]
    assert sent["name"] == SITE and sent["skip_backups"] is False
    assert sent["skip_failing_patches"] is False


def test_deploy_waits_for_late_site_move(dfc, cli):
    """FC moves the site in a separate job after the bench is ready (seen live 2026-11-09)."""
    done = info(has_running_release_pipeline=False)
    moved = info(has_running_release_pipeline=False)
    moved["sites"][0]["bench"] = "bench-3"
    dfc.deploy_infos["bench-1234"] = [
        info(),
        info(has_running_release_pipeline=True),
        done,
        done,
        moved,
    ]
    result = cli(
        "bench-deploy", "bench-1234", "--app", "hrms", "--site", SITE,
        "--confirm", "bench-1234",
    )  # fmt: skip
    assert result.code == 0, result.err
    assert f"{SITE} (waiting)" in result.err + result.out
    assert f"{SITE} (updated)" in result.out


def test_deploy_site_not_confirmed_in_time_exits_6(dfc, cli, monkeypatch):
    from fc_manager import deploy as deploy_module

    monkeypatch.setattr(deploy_module, "SITE_UPDATE_LIMIT_SECONDS", 0)
    finish_infos(dfc, site_bench="bench-2")
    result = cli(
        "bench-deploy", "bench-1234", "--app", "hrms", "--site", SITE,
        "--confirm", "bench-1234",
    )  # fmt: skip
    assert result.code == 6
    assert "did not confirm the update of " + SITE in result.err
    assert "not known" in result.err
    assert len(dfc.posts) == 1


def test_no_wait_returns_after_post(dfc, cli):
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234", "--no-wait")
    assert result.code == 0, result.err
    assert "fcm bench-show bench-1234" in result.out
    assert len(dfc.posts) == 1
    assert not any(m.endswith("deploy_status") for m, _, _ in dfc.teams_seen)


def test_build_failure_exits_8_with_step(dfc, cli):
    dfc.builds = [build("Failure", failed_at=2)]
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234")
    assert result.code == 8
    assert "Run Validations: Pre-build" in result.err
    assert "pip install failed" in result.err


def test_validation_error_on_post_is_not_retried(dfc, cli):
    message = json.dumps([json.dumps({"message": "This deploy will fail"})])
    dfc.post_error = (417, {"exc_type": "BuildValidationError", "_server_messages": message})
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234")
    assert result.code == 1
    assert "This deploy will fail" in result.err
    assert len(dfc.posts) == 1


def test_ctrl_c_during_watch_stops_watching_only(dfc, cli, monkeypatch):
    def interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(deploy_cli.time, "sleep", interrupt)
    result = cli("bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234")
    assert result.code == 130
    assert "The deploy continues on FC" in result.out
    assert "fcm bench-show bench-1234" in result.out
    assert len(dfc.posts) == 1
    calls = len(dfc.teams_seen)
    assert dfc.teams_seen[-1][2] == "GET" and calls > 0


# --- 5.2 / 5.3 interactive walk -------------------------------------------------------


@pytest.fixture
def tty(monkeypatch):
    """Interactive mode with scripted picker answers."""
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    seen = {"many": [], "text": []}
    answers = {"many": [], "text": []}

    def choose_many(prompt, options, *, selected, back=True, path=None):
        seen["many"].append(
            {"prompt": prompt, "selected": selected, "options": options, "path": path}
        )
        answer = answers["many"].pop(0)
        if answer is picker.GoBack:
            raise picker.GoBack
        return answer if answer != "all" else [value for _, value in options]

    def ask_text(prompt):
        seen["text"].append(prompt)
        return answers["text"].pop(0)

    monkeypatch.setattr(picker, "choose_many", choose_many)
    monkeypatch.setattr(picker, "ask_text", ask_text)
    return seen, answers


def test_interactive_defaults_and_typed_title(dfc, cli, tty):
    seen, answers = tty
    finish_infos(dfc)
    answers["many"] = ["all", []]
    answers["text"] = ["ACME Prod"]
    result = cli("bench-deploy", "bench-1234")
    assert result.code == 0, result.err
    apps_step, sites_step = seen["many"]
    assert apps_step["selected"] is True
    assert sites_step["selected"] is False
    assert [v for _, v in sites_step["options"]] == [SITE]
    assert "ACME Prod" in seen["text"][0]
    assert "Deploy preview" in result.out and "Bench only" in result.out
    assert len(dfc.posts) == 1 and dfc.posts[0]["sites"] == []


@pytest.mark.parametrize("typed", ["", "acme prod", "bench-1234", "ACME Prod "])
def test_interactive_wrong_title_sends_nothing(dfc, cli, tty, typed):
    _, answers = tty
    answers["many"] = ["all", []]
    answers["text"] = [typed]
    result = cli("bench-deploy", "bench-1234")
    assert result.code == 2
    assert "Nothing was sent to FC" in result.err
    assert dfc.posts == []


def test_interactive_esc_on_sites_goes_back_to_apps(dfc, cli, tty):
    seen, answers = tty
    answers["many"] = ["all", picker.GoBack, ["hrms"], []]
    answers["text"] = ["nope"]
    cli("bench-deploy", "bench-1234")
    prompts = [s["prompt"].split()[0] for s in seen["many"]]
    assert prompts == ["App", "Sites", "App", "Sites"]
    assert dfc.posts == []


def test_interactive_empty_app_selection_asks_again(dfc, cli, tty):
    seen, answers = tty
    answers["many"] = [[], ["hrms"], []]
    answers["text"] = ["nope"]
    result = cli("bench-deploy", "bench-1234")
    assert "Select at least one app to deploy." in result.out
    assert [s["prompt"].split()[0] for s in seen["many"]] == ["App", "App", "Sites"]


def test_interactive_site_step_shown_with_no_site(dfc, cli, tty):
    _, answers = tty
    dfc.deploy_infos["bench-1234"] = [info(sites=[])]
    answers["many"] = ["all"]
    answers["text"] = ["nope"]
    result = cli("bench-deploy", "bench-1234")
    assert "No active site on this bench: the deploy is bench only." in result.out


def test_interactive_bench_picker_and_esc_back_to_bench(dfc, cli, tty, monkeypatch):
    seen, answers = tty
    picks = []

    def choose(prompt, options, *, back=False):
        picks.append([label for label, _ in options])
        return next(b for _, b in options if b.name == "bench-1234")

    monkeypatch.setattr(picker, "choose", choose)
    answers["many"] = [picker.GoBack, "all", []]
    answers["text"] = ["nope"]
    cli("bench-deploy", "--team", "team-acme")
    assert len(picks) == 2  # the bench step, then again after Esc on the app step
    assert any("ACME Prod (bench-1234)" in label for label in picks[0])
    assert {team for _, team, _ in dfc.teams_seen if team} == {"team-acme"}
    assert dfc.posts == []


def scripted_choose(monkeypatch, script):
    """Patch picker.choose: each entry picks by FC name, or is picker.GoBack."""
    prompts = []

    def choose(prompt, options, *, back=False, path=None):
        prompts.append((prompt, [label for label, _ in options], back))
        answer = script.pop(0)
        if answer is picker.GoBack:
            raise picker.GoBack
        return next(value for _, value in options if value.name == answer)

    monkeypatch.setattr(picker, "choose", choose)
    return prompts


def test_walk_picks_team_then_bench_of_that_team(dfc, cli, tty, monkeypatch):
    _, answers = tty
    prompts = scripted_choose(monkeypatch, ["team-acme", "bench-1234"])
    answers["many"] = ["all", []]
    answers["text"] = ["nope"]
    cli("bench-deploy", "--dry-run")
    (team_prompt, team_labels, _), (bench_prompt, bench_labels, bench_back) = prompts
    assert team_prompt == "Team" and len(team_labels) == 3
    assert any("acme@example.com" in label for label in team_labels)
    assert bench_prompt == "Bench in ACME Corp"
    assert bench_labels == ["ACME Prod (bench-1234)", "Prod (bench-1240)"]
    assert bench_back is True
    # bench.all went to the picked team only; no fan-out over all teams.
    bench_calls = [t for m, t, _ in dfc.teams_seen if m == "press.api.bench.all"]
    assert bench_calls == ["team-acme"]


def test_esc_on_bench_step_goes_back_to_team_step(dfc, cli, tty, monkeypatch):
    _, answers = tty
    prompts = scripted_choose(monkeypatch, ["team-beta", picker.GoBack, "team-acme", "bench-1234"])
    answers["many"] = ["all", []]
    answers["text"] = ["nope"]
    cli("bench-deploy", "--dry-run")
    assert [p[0].split()[0] for p in prompts] == ["Team", "Bench", "Team", "Bench"]


def test_esc_on_app_step_goes_back_to_bench_step_of_same_team(dfc, cli, tty, monkeypatch):
    _, answers = tty
    prompts = scripted_choose(monkeypatch, ["team-acme", "bench-1234", "bench-1234"])
    answers["many"] = [picker.GoBack, "all", []]
    answers["text"] = ["nope"]
    cli("bench-deploy", "--dry-run")
    assert [p[0].split()[0] for p in prompts] == ["Team", "Bench", "Bench"]
    assert prompts[2][1] == ["ACME Prod (bench-1234)", "Prod (bench-1240)"]


def test_bench_show_uses_the_same_walk(dfc, cli, monkeypatch):
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    prompts = scripted_choose(monkeypatch, ["team-acme", "bench-1234"])
    result = cli("bench-show")
    assert result.code == 0, result.err
    assert [p[0].split()[0] for p in prompts] == ["Team", "Bench"]


# --- watch screen: liveness from real FC answers ---------------------------------------


def _render(view) -> str:
    from rich.console import Console

    console = Console(width=200, record=True, color_system=None)
    console.print(view)
    return console.export_text()


def _running_state(at: float, polls: int):
    from fc_manager.deploy import BuildStep, DeployState

    steps = (
        BuildStep("Clone", "Frappe", "Success", "0.4s", True),
        BuildStep("Install apps", "", "Running", "", False),
    )
    return DeployState(stage="building", build="b-new", steps=steps, checked_at=at, polls=polls)


def test_watch_view_counts_from_last_fc_answer():
    from fc_manager.cli.deploy import _WatchView

    now = [100.0]
    view = _WatchView("ACME Prod", clock=lambda: now[0])
    view.update(_running_state(at=100.0, polls=1))
    now[0] = 103.0
    view.update(_running_state(at=103.0, polls=2))  # same FC data, new answer
    now[0] = 105.0
    text = _render(view)
    assert "Deploy ACME Prod: building the new bench image - Install apps" in text
    assert "last FC answer 2 s ago (poll 2)" in text
    assert "running 5 s" in text  # from the first poll that saw the step Running
    assert "elapsed 5 s" in text


def test_watch_view_warns_when_fc_does_not_answer():
    from fc_manager.cli.deploy import _WatchView

    now = [100.0]
    view = _WatchView("ACME Prod", clock=lambda: now[0])
    view.update(_running_state(at=100.0, polls=1))
    now[0] = 114.0  # a poll hangs: no new state for 14 s
    text = _render(view)
    assert "no answer from FC for 14 s" in text
    assert "last FC answer" not in text


def test_watch_view_final_line_has_no_counter():
    from fc_manager.cli.deploy import _WatchView

    now = [100.0]
    view = _WatchView("ACME Prod", clock=lambda: now[0])
    view.update(_running_state(at=100.0, polls=1))
    view.done = True
    now[0] = 190.0
    text = _render(view)
    assert "elapsed 1m30s" in text
    assert "FC answer" not in text and "running " not in text


# --- cli-hub 2.2 / 2.3: work functions for the menu ----------------------------------------


def _menu_session():
    from fc_manager.cli.common import session

    return session(None, False, False)


def _bench(s):
    return deploy_cli._resolve_bench(s, deploy_cli.scope_teams(s, None), "bench-1234")


def test_deploy_bench_in_menu_esc_on_apps_goes_up(dfc, tty):
    seen, answers = tty
    answers["many"] = [picker.GoBack]
    with _menu_session() as s, pytest.raises(picker.GoBack):
        deploy_cli.deploy_bench(
            s, _bench(s), deploy_cli.DeployOptions(), in_menu=True, path="env > ACME > X"
        )
    assert seen["many"][0]["path"] == "env > ACME > X"
    assert dfc.posts == []


def test_deploy_bench_in_menu_ctrl_c_in_watch_raises_watch_stopped(dfc, tty, monkeypatch, capsys):
    def interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(deploy_cli.time, "sleep", interrupt)
    _, answers = tty
    answers["many"] = ["all", []]
    answers["text"] = ["ACME Prod"]
    with _menu_session() as s, pytest.raises(deploy_cli.WatchStopped):
        deploy_cli.deploy_bench(s, _bench(s), deploy_cli.DeployOptions(), in_menu=True)
    assert len(dfc.posts) == 1
    assert "The deploy continues on FC" in capsys.readouterr().out


def test_direct_command_passes_no_path(dfc, cli, tty):
    seen, answers = tty
    answers["many"] = ["all", []]
    answers["text"] = ["nope"]
    cli("bench-deploy", "bench-1234")
    assert all(entry["path"] is None for entry in seen["many"])
