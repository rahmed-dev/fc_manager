"""Group 3: top-level handler, CLI grammar, picker."""

import json

import pytest
import typer

from fc_manager.cli import app as app_module
from fc_manager.cli import picker
from fc_manager.cli.app import NOUNS, READ_VERBS, WRITE_VERBS, app
from fc_manager.errors import UsageError

# --- 3.2: top-level handler -----------------------------------------------------------


@pytest.fixture
def boom(monkeypatch):
    """Make `fcm team list` raise an unexpected exception that holds a secret."""
    from fc_manager.cli import inventory

    def explode(*_args, **_kwargs):
        raise RuntimeError("kaboom with secret-2222bbbb inside")

    monkeypatch.setattr(inventory, "session", explode)


def test_unexpected_exception_exits_1_without_traceback(env, cli, boom):
    from fc_manager.redact import register

    register("secret-2222bbbb")
    result = cli("team", "list")
    assert result.code == 1
    assert "Traceback" not in result.err
    assert "Unexpected error: RuntimeError" in result.err
    assert "--debug" in result.err
    assert "secret-2222bbbb" not in result.err


def test_unexpected_exception_with_debug_shows_redacted_traceback(env, cli, boom):
    from fc_manager.redact import register

    register("secret-2222bbbb")
    result = cli("team", "list", "--debug")
    assert result.code == 1
    assert "Traceback" in result.err
    assert "secret-2222bbbb" not in result.err


def test_usage_error_from_parser_exits_2(env, cli):
    result = cli("site", "list", "--status", "nonsense")
    assert result.code == 2


# --- 3.3: grammar ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("plural", "suggestion"),
    [("sites", "fcm site list"), ("benches", "fcm bench list"), ("teams", "fcm team list")],
)
def test_plural_noun_suggests_singular_list(env, cli, plural, suggestion):
    result = cli(plural)
    assert result.code == 2
    assert suggestion in result.err


def test_site_show_without_target_in_json_mode_exits_2(env, cli):
    result = cli("site", "show", "--json")
    assert result.code == 2
    payload = json.loads(result.err)
    assert payload["kind"] == "usage"
    assert result.out == ""


def test_every_command_is_noun_verb_with_a_fixed_verb():
    root = typer.main.get_command(app)
    ctx = typer.Context(root)
    assert sorted(root.list_commands(ctx)) == sorted(NOUNS)
    for noun in NOUNS:
        group = root.get_command(ctx, noun)
        verbs = group.list_commands(typer.Context(group))
        assert verbs, noun
        for verb in verbs:
            assert verb in READ_VERBS | WRITE_VERBS, f"fcm {noun} {verb}: verb not in the fixed set"
            command = group.get_command(typer.Context(group), verb)
            assert not hasattr(command, "list_commands"), f"fcm {noun} {verb} nests deeper"


def test_shared_options_mean_the_same_everywhere():
    root = typer.main.get_command(app)
    ctx = typer.Context(root)
    for noun in NOUNS:
        group = root.get_command(ctx, noun)
        for verb in group.list_commands(typer.Context(group)):
            command = group.get_command(typer.Context(group), verb)
            options = {opt for p in command.params for opt in getattr(p, "opts", [])}
            assert "--json" in options and "--debug" in options, f"fcm {noun} {verb}"


# --- 3.4: picker ----------------------------------------------------------------------


def test_is_interactive_false_with_json(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    assert picker.is_interactive(json_mode=True) is False


def test_is_interactive_false_when_stdout_is_piped(capsys):
    # capsys replaces stdout with a non-terminal stream
    assert picker.is_interactive(json_mode=False) is False


def test_pick_or_fail_never_prompts_when_not_interactive(monkeypatch):
    def fail(*_a, **_k):
        raise AssertionError("questionary must not be called")

    monkeypatch.setattr(picker.questionary, "select", fail)
    with pytest.raises(UsageError) as info:
        picker.pick_or_fail(
            interactive=False,
            prompt="Bench",
            options=[("Prod (bench-1240)  - ACME Corp", 1), ("Prod (bench-0981)  - Beta Ltd", 2)],
            problem="Bench 'Prod' matches 2 benches",
        )
    assert "bench-1240" in info.value.hint and "ACME Corp" in info.value.hint
    assert "bench-0981" in info.value.hint and "Beta Ltd" in info.value.hint


class FakeQuestion:
    def __init__(self, answer):
        self.answer = answer

    def ask(self):
        return self.answer


def test_picker_returns_choice(monkeypatch):
    seen = {}

    def select(prompt, choices, **kwargs):
        seen.update(kwargs, titles=[c.title for c in choices])
        return FakeQuestion(1)

    monkeypatch.setattr(picker.questionary, "select", select)
    value = picker.pick_or_fail(
        interactive=True, prompt="Site", options=[("a", "A"), ("b", "B")], problem="x"
    )
    assert value == "B"
    assert seen["use_search_filter"] is True
    assert seen["titles"] == ["a", "b"]


def test_picker_cancel_raises_usage_error_exit_2(monkeypatch):
    monkeypatch.setattr(picker.questionary, "select", lambda *a, **k: FakeQuestion(None))
    with pytest.raises(UsageError) as info:
        picker.choose("Site", [("a", 1)])
    assert info.value.exit_code == 2


def test_main_exits_with_run_code(monkeypatch):
    monkeypatch.setattr(app_module, "run", lambda args: 5)
    monkeypatch.setattr("sys.argv", ["fcm", "x"])
    with pytest.raises(SystemExit) as info:
        app_module.main()
    assert info.value.code == 5
