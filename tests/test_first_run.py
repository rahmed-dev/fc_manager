"""release-v1 group 1 and 2: first-run setup in the menu entry, and `fcm --version`."""

import json
from importlib.metadata import version as package_version

import httpx
import pytest
import respx

from fc_manager import config, credentials
from fc_manager.cli import menu as menu_cli
from fc_manager.cli import picker
from fc_manager.cli import profile as profile_cli

from .conftest import KEY, SECRET, fixture, method_url, save_profile


@pytest.fixture
def terminal(env, monkeypatch):
    """A terminal, typed setup answers, and a recorded menu run (no FC walk)."""
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    monkeypatch.setattr(profile_cli, "_prompt_key", lambda: KEY)
    monkeypatch.setattr(profile_cli, "_prompt_secret", lambda: SECRET)
    asked = []

    def prompt(text, default=None, **_kw):
        asked.append((text, default))
        return default

    monkeypatch.setattr(menu_cli.typer, "prompt", prompt)
    opened = []
    monkeypatch.setattr(menu_cli, "run", lambda profile: opened.append(profile))
    return asked, opened


@respx.mock
def test_first_run_adds_the_profile_and_opens_the_menu(terminal, cli, memkeyring):
    asked, opened = terminal
    account = respx.get(method_url("press.api.account.get")).respond(
        json=fixture("account_get.json")
    )
    result = cli()
    assert result.code == 0, result.err
    assert "Welcome to fcm" in result.out and "API Access" in result.out
    assert asked == [("Profile name", "default")]
    assert account.called and account.calls.last.request.method == "GET"
    assert config.load().default_profile == "default"
    assert json.loads(memkeyring.store[("fc_manager", "default")])["api_key"] == KEY
    assert "Profile default saved: user user@example.com" in result.out
    assert opened == ["default"]
    assert SECRET not in result.out + result.err


@respx.mock
def test_first_run_rejected_key_stores_nothing(terminal, cli, memkeyring):
    _, opened = terminal
    respx.get(method_url("press.api.account.get")).respond(401, json=fixture("error_auth.json"))
    result = cli()
    assert result.code == 3
    assert memkeyring.store == {} and config.load().profiles == {}
    assert opened == []


def test_first_run_without_keyring_asks_nothing(terminal, cli, monkeypatch):
    asked, opened = terminal
    monkeypatch.setattr(credentials, "keyring_usable", lambda backend=None: False)
    result = cli()
    assert result.code == 2
    assert credentials.ENV_KEY in result.err and credentials.ENV_SECRET in result.err
    assert asked == [] and opened == []


def test_env_credentials_skip_the_setup(terminal, cli, monkeypatch):
    asked, opened = terminal
    monkeypatch.setenv(credentials.ENV_KEY, KEY)
    monkeypatch.setenv(credentials.ENV_SECRET, SECRET)
    assert cli().code == 0
    assert asked == [] and opened == [None]


def test_saved_profile_skips_the_setup(terminal, cli):
    asked, opened = terminal
    save_profile("work")
    assert cli().code == 0
    assert asked == [] and opened == [None]


def test_profile_option_skips_the_setup(terminal, cli):
    asked, _ = terminal
    cli("--profile", "work")
    assert asked == []


def test_no_terminal_prints_help_and_asks_nothing(env, cli, monkeypatch):
    monkeypatch.setattr(menu_cli, "first_run", lambda: pytest.fail("setup on no terminal"))
    result = cli()
    assert result.code == 0 and "Usage" in result.out


def test_ctrl_c_in_the_setup_exits_130(terminal, cli, monkeypatch, memkeyring):
    import typer

    def abort(*_a, **_k):
        raise typer.Abort

    monkeypatch.setattr(menu_cli.typer, "prompt", abort)
    result = cli()
    assert result.code == 130
    assert memkeyring.store == {}


def test_version_prints_and_reads_nothing(env, cli, monkeypatch):
    monkeypatch.setattr(credentials, "resolve", lambda *a: pytest.fail("credentials read"))
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("FC request"))
    result = cli("--version")
    assert result.code == 0
    assert result.out.strip() == f"fcm {package_version('fc-manager')}"


@respx.mock
def test_first_run_rejected_key_hint_is_the_setup(terminal, cli):
    respx.get(method_url("press.api.account.get")).respond(401, json=fixture("error_auth.json"))
    result = cli()
    assert "Run fcm again to retry the setup" in result.err
    assert "profile-add" not in result.err


@pytest.mark.parametrize(
    ("key", "secret"),
    [("Key: abc123", "def456"), ("abc123 def456", "x"), ("abc123", "Secret: def456")],
)
def test_pasted_label_or_pair_is_refused_before_fc(env, cli, monkeypatch, memkeyring, key, secret):
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    monkeypatch.setattr(profile_cli, "_prompt_key", lambda: key)
    monkeypatch.setattr(profile_cli, "_prompt_secret", lambda: secret)
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("FC request"))
    result = cli("profile-add", "work")
    assert result.code == 2
    assert "does not look like an FC API" in result.err and "Nothing was sent" in result.err
    assert "def456" not in result.err and "abc123" not in result.err
    assert memkeyring.store == {}
