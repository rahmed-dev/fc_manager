"""Group 4: config file, credential storage, profile commands."""

import json
import stat

import httpx
import keyring
import pytest
import respx

from fc_manager import config, credentials
from fc_manager.cli import picker
from fc_manager.cli import profile as profile_cli
from fc_manager.errors import UsageError
from fc_manager.redact import Credentials

from .conftest import BASE, KEY, SECRET, fixture, method_url, save_profile

# --- 4.1: config file -----------------------------------------------------------------


def test_config_round_trip_mode_0600_and_no_secrets(env):
    cfg = config.Config(
        default_profile="work",
        profiles={"work": config.Profile("work", BASE), "client": config.Profile("client", BASE)},
    )
    path = config.save(cfg)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    loaded = config.load()
    assert loaded.default_profile == "work"
    assert set(loaded.profiles) == {"work", "client"}
    text = path.read_text()
    assert "api_key" not in text and "api_secret" not in text


def test_missing_config_is_empty(env):
    assert config.load().profiles == {}


def test_damaged_config_is_a_usage_error(env):
    path = config.config_path()
    path.parent.mkdir(parents=True)
    path.write_text("this is = = not toml")
    with pytest.raises(UsageError):
        config.load()


# --- 4.2: credentials -----------------------------------------------------------------


def test_store_and_load_round_trip(env, memkeyring):
    credentials.store("work", Credentials(KEY, SECRET))
    assert len(memkeyring.store) == 1  # one entry per profile
    creds = credentials.load("work")
    assert (creds.api_key, creds.api_secret) == (KEY, SECRET)


def test_unsafe_backends_are_rejected():
    from keyring.backends import fail, null

    assert credentials.keyring_usable(fail.Keyring()) is False
    assert credentials.keyring_usable(null.Keyring()) is False


def test_store_refuses_without_keyring(env, monkeypatch):
    monkeypatch.setattr(credentials, "keyring_usable", lambda backend=None: False)
    with pytest.raises(UsageError) as info:
        credentials.store("work", Credentials(KEY, SECRET))
    assert credentials.ENV_KEY in info.value.hint


def test_env_credentials_win_and_keyring_is_not_read(env, monkeypatch):
    save_profile("work")
    monkeypatch.setenv(credentials.ENV_KEY, "env-key-9999")
    monkeypatch.setenv(credentials.ENV_SECRET, "env-secret-9999")
    monkeypatch.setattr(credentials, "load", lambda name: pytest.fail("keyring must not be read"))
    active = credentials.resolve(None, config.load())
    assert active.credentials.api_key == "env-key-9999"
    assert active.from_env is True


@pytest.mark.parametrize(
    ("set_var", "missing"),
    [(credentials.ENV_KEY, credentials.ENV_SECRET), (credentials.ENV_SECRET, credentials.ENV_KEY)],
)
def test_one_env_variable_is_a_config_error(env, monkeypatch, set_var, missing):
    monkeypatch.setenv(set_var, "value-1234")
    with pytest.raises(UsageError) as info:
        credentials.env_credentials()
    assert missing in info.value.message


def test_profile_selection_order(env, monkeypatch):
    save_profile("work")
    save_profile("client", default=False)
    cfg = config.load()
    assert credentials.resolve(None, cfg).label == "work"
    monkeypatch.setenv(credentials.ENV_PROFILE, "client")
    assert credentials.resolve(None, cfg).label == "client"
    assert credentials.resolve("work", cfg).label == "work"


def test_no_profile_configured(env):
    with pytest.raises(UsageError) as info:
        credentials.resolve(None, config.load())
    assert "fcm profile-add" in info.value.hint


def test_unknown_profile(env):
    save_profile("work")
    with pytest.raises(UsageError):
        credentials.resolve("nope", config.load())


# --- 4.3: profile add -----------------------------------------------------------------


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)


@pytest.fixture
def typed(monkeypatch):
    def set_answers(key=KEY, secret=SECRET):
        monkeypatch.setattr(profile_cli, "_prompt_key", lambda: key)
        monkeypatch.setattr(profile_cli, "_prompt_secret", lambda: secret)

    set_answers()
    return set_answers


@respx.mock
def test_add_valid_credentials(env, cli, interactive, typed, memkeyring):
    respx.get(method_url("press.api.account.get")).respond(json=fixture("account_get.json"))
    result = cli("profile-add", "work")
    assert result.code == 0, result.err
    assert "user@example.com" in result.out and "13 teams" in result.out
    assert config.load().default_profile == "work"
    assert json.loads(memkeyring.store[("fc_manager", "work")])["api_secret"] == SECRET
    assert SECRET not in result.out + result.err


@respx.mock
def test_add_rejected_credentials_stores_nothing(env, cli, interactive, typed, memkeyring):
    respx.get(method_url("press.api.account.get")).respond(401, json=fixture("error_auth.json"))
    result = cli("profile-add", "work")
    assert result.code == 3
    assert "FC dashboard" in result.err
    assert memkeyring.store == {}
    assert config.load().profiles == {}


def test_add_duplicate_name_is_refused(env, cli, interactive, typed):
    save_profile("work")
    result = cli("profile-add", "work")
    assert result.code == 2
    assert "--replace" in result.err


@respx.mock
def test_add_replace_updates_credentials(env, cli, interactive, typed, memkeyring):
    save_profile("work", key="old-key-0000", secret="old-secret-0000")
    respx.get(method_url("press.api.account.get")).respond(json=fixture("account_get.json"))
    result = cli("profile-add", "work", "--replace")
    assert result.code == 0, result.err
    assert credentials.load("work").api_secret == SECRET


def test_add_secret_is_never_a_cli_argument():
    import typer

    from fc_manager.cli.app import app

    root = typer.main.get_command(app)
    add = root.get_command(typer.Context(root), "profile-add")
    names = {opt for p in add.params for opt in getattr(p, "opts", [])}
    assert not any("secret" in n or "key" in n for n in names), names


def test_add_rejects_http_base_url(env, cli, interactive, typed):
    result = cli("profile-add", "work", "--base-url", "http://example.com")
    assert result.code == 2
    assert "HTTPS" in result.err


def test_add_without_keyring(env, cli, interactive, typed, monkeypatch):
    monkeypatch.setattr(credentials, "keyring_usable", lambda backend=None: False)
    result = cli("profile-add", "work")
    assert result.code == 2
    assert credentials.ENV_KEY in result.err
    assert config.load().profiles == {}


def test_add_needs_a_terminal(env, cli, typed):
    result = cli("profile-add", "work")
    assert result.code == 2
    assert "terminal" in result.err


# --- 4.4: list, test, remove ----------------------------------------------------------


def test_list_shows_names_and_default_without_credentials(env, cli):
    save_profile("work")
    save_profile("client", default=False)
    result = cli("profile-list")
    assert result.code == 0
    assert "work" in result.out and "client" in result.out and "*" in result.out
    assert KEY not in result.out and SECRET not in result.out


def test_list_json(env, cli):
    save_profile("work")
    rows = json.loads(cli("profile-list", "--json").out)
    assert rows == [{"name": "work", "default": True, "base_url": BASE}]


def test_list_empty(env, cli):
    assert "No profiles" in cli("profile-list").out


@respx.mock
def test_test_reports_user_and_teams(env, cli):
    save_profile("work")
    respx.get(method_url("press.api.account.get")).respond(json=fixture("account_get.json"))
    result = cli("profile-test", "work")
    assert result.code == 0
    assert "user@example.com" in result.out
    assert "name-14" in result.out


@respx.mock
def test_test_revoked_key_hints_replace(env, cli):
    save_profile("work")
    respx.get(method_url("press.api.account.get")).respond(401, json=fixture("error_auth.json"))
    result = cli("profile-test", "work")
    assert result.code == 3
    assert "fcm profile-add work --replace" in result.err


def test_remove_with_confirmation(env, cli, interactive, monkeypatch, memkeyring):
    save_profile("work")
    monkeypatch.setattr(profile_cli, "_confirm", lambda q: True)
    result = cli("profile-remove", "work")
    assert result.code == 0
    assert config.load().profiles == {}
    assert memkeyring.store == {}


def test_remove_cancelled_changes_nothing(env, cli, interactive, monkeypatch, memkeyring):
    save_profile("work")
    monkeypatch.setattr(profile_cli, "_confirm", lambda q: False)
    result = cli("profile-remove", "work")
    assert result.code == 0
    assert "work" in config.load().profiles
    assert memkeyring.store


def test_remove_non_interactive_needs_yes(env, cli, memkeyring):
    save_profile("work")
    assert cli("profile-remove", "work").code == 2
    assert cli("profile-remove", "work", "--yes").code == 0
    assert config.load().profiles == {}


def test_remove_moves_default(env, cli):
    save_profile("work")
    save_profile("client", default=False)
    cli("profile-remove", "work", "--yes")
    assert config.load().default_profile == "client"


def test_keyring_errors_are_usage_errors(env, monkeypatch):
    def broken(*_a):
        raise keyring.errors.KeyringLocked("locked")

    monkeypatch.setattr(keyring, "get_password", broken)
    with pytest.raises(UsageError):
        credentials.load("work")


def test_httpx_is_not_called_for_list(env, cli, monkeypatch):
    save_profile("work")
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("no network"))
    assert cli("profile-list").code == 0
