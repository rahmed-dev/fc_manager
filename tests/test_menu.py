"""cli-hub group 3: `fcm` with no command opens the menu (team, bench, action)."""

# ruff: noqa: F811 - the dfc and tty fixtures come from test_cli_deploy

import pytest

from fc_manager.cli import deploy as deploy_cli
from fc_manager.cli import picker
from fc_manager.errors import PermissionDenied

from .test_cli_deploy import dfc, tty  # noqa: F401 - shared fixtures

BACK = picker.GoBack
CTRL_C = picker.Cancelled


@pytest.fixture
def menu(monkeypatch):
    """Scripted picker.choose for the menu. Each answer is a team or bench FC name, an
    action value, BACK (Esc), or CTRL_C. Records (prompt, labels, path) for each prompt."""
    script: list = []
    prompts: list = []

    def choose(prompt, options, *, back=False, path=None):
        prompts.append((prompt, [label for label, _ in options], path))
        answer = script.pop(0)
        if answer is BACK:
            raise picker.GoBack
        if answer is CTRL_C:
            raise picker.Cancelled("Cancelled, nothing done")
        for _, value in options:
            if getattr(value, "name", value) == answer:
                return value
        raise AssertionError(f"{answer!r} not offered at {prompt!r}")

    monkeypatch.setattr(picker, "choose", choose)
    return script, prompts


def names(prompts):
    return [prompt for prompt, _, _ in prompts]


def test_fcm_without_terminal_prints_help(env, cli):
    result = cli()
    assert result.code == 0
    assert "Usage" in result.out and "bench-deploy" in result.out


def test_team_then_bench_of_that_team_then_show(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", "show", "quit"]
    result = cli()
    assert result.code == 0, result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    assert prompts[0][2] == "work"
    assert prompts[1][1] == ["ACME Prod (bench-1234)", "Prod (bench-1240)"]  # team-acme only
    assert prompts[2][2] == "work > ACME Corp > ACME Prod (bench-1234)"
    assert "Bench ACME Prod" in result.out  # the bench-show output
    bench_calls = [team for method, team, _ in dfc.teams_seen if method.endswith("bench.all")]
    assert bench_calls == ["team-acme"]


def test_action_menu_names_the_direct_commands(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", "quit"]
    cli()
    assert prompts[2][1] == [
        "Show bench (bench-show)",
        "Deploy app updates (bench-deploy)",
        "Pick another bench",
        "Quit",
    ]


def test_wrong_title_sends_nothing_and_returns_to_actions(dfc, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "deploy", "quit"]
    answers["many"] = ["all", []]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    assert dfc.posts == []
    assert "ancelled" in result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    # 3.5: GET only, and after the bench pick only the picked team.
    assert {verb for _, _, verb in dfc.teams_seen} == {"GET"}
    assert {team for _, team, _ in after_bench_pick_calls(dfc)} == {"team-acme"}


def after_bench_pick_calls(fc):
    first = next(i for i, c in enumerate(fc.teams_seen) if c[0].endswith("deploy_information"))
    return fc.teams_seen[first:]


def test_action_error_is_printed_and_menu_stays(dfc, cli, tty, menu, monkeypatch):
    def denied(s, bench):
        raise PermissionDenied("Not permitted", target="team ACME", hint="Ask the owner.")

    monkeypatch.setattr(deploy_cli, "show_bench", denied)
    script, prompts = menu
    script += ["team-acme", "bench-1234", "show", "quit"]
    result = cli()
    assert result.code == 0
    assert "Not permitted" in result.err and "Ask the owner." in result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]


def test_esc_walks_back_one_step_and_out(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", BACK, BACK, BACK]
    result = cli()
    assert result.code == 0
    assert names(prompts) == ["Team", "Bench", "Action", "Bench", "Team"]
    assert dfc.posts == []


def test_esc_at_deploy_app_step_returns_to_actions(dfc, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "deploy", "quit"]
    answers["many"] = [picker.GoBack]
    result = cli()
    assert result.code == 0, result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    assert dfc.posts == []


def test_ctrl_c_at_menu_prompt_exits_130(dfc, cli, tty, menu):
    script, _ = menu
    script += ["team-acme", CTRL_C]
    result = cli()
    assert result.code == 130
    assert dfc.posts == []


def test_other_bench_entry_goes_to_bench_step(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", "bench", "bench-1240", "quit"]
    result = cli()
    assert result.code == 0
    assert names(prompts) == ["Team", "Bench", "Action", "Bench", "Action"]
    assert prompts[4][2] == "work > ACME Corp > Prod (bench-1240)"
