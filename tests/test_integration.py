"""Group 6: integration checks across every command.

6.1  A canary key and secret must never appear in stdout or stderr, on any error path,
     with or without --debug and --json.
6.2  Every command requests only allowlisted FC methods.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from fc_manager.api import client as client_module
from fc_manager.api.client import READ_ONLY_METHODS
from fc_manager.cli.app import NOUNS, app
from fc_manager.inventory import Inventory

from .conftest import BASE, default_fake, fixture, save_profile

CANARY_KEY = "canaryKEY-7f3a9c"
CANARY_SECRET = "canarySECRET-91be4d"

COMMANDS = [
    ["team", "list"],
    ["bench", "list"],
    ["site", "list"],
    ["site", "list", "--bench", "ACME Prod"],
    ["site", "show", "erp.acme.example.com"],
    ["profile", "test", "work"],
]

FLAGS = [[], ["--debug"], ["--json"], ["--debug", "--json"]]


def _echo_headers(request: httpx.Request) -> str:
    # A hostile or broken proxy that echoes the request headers back in its error page.
    return f"<html>bad gateway; you sent Authorization: {request.headers['Authorization']}</html>"


def error_path(name: str):
    """Return an httpx handler that fails every request in the named way."""

    def handler(request: httpx.Request) -> httpx.Response:
        if name == "auth":
            return httpx.Response(401, json=fixture("error_auth.json"))
        if name == "permission":
            return httpx.Response(403, json=fixture("error_permission.json"))
        if name == "not_found":
            return httpx.Response(404, json=fixture("error_not_found.json"))
        if name == "server":
            return httpx.Response(500, json={"exception": f"Boom {request.headers}"})
        if name == "timeout":
            raise httpx.ReadTimeout(f"timed out {request.headers}", request=request)
        if name == "non_json":
            return httpx.Response(502, text=_echo_headers(request))
        raise AssertionError(name)

    return handler


ERROR_PATHS = ["auth", "permission", "not_found", "server", "timeout", "non_json", "unexpected"]


@pytest.fixture
def canary_profile(env, monkeypatch):
    save_profile("work", key=CANARY_KEY, secret=CANARY_SECRET)
    monkeypatch.setattr(client_module, "BACKOFF_SECONDS", (0.0, 0.0))


@pytest.mark.parametrize("path", ERROR_PATHS)
@pytest.mark.parametrize("flags", FLAGS, ids=lambda f: " ".join(f) or "plain")
@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_canary_never_leaks(canary_profile, cli, monkeypatch, command, flags, path):
    if path == "unexpected":
        fake = default_fake()

        def explode(self):
            raise RuntimeError(f"surprise Token {CANARY_KEY}:{CANARY_SECRET}")

        monkeypatch.setattr(Inventory, "account", explode)
        handler = fake.handle
    else:
        handler = error_path(path)

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.route().mock(side_effect=handler)
        result = cli(*command, *flags)

    assert result.code != 0
    for stream in (result.out, result.err):
        assert CANARY_KEY not in stream
        assert CANARY_SECRET not in stream


@pytest.mark.parametrize("flags", FLAGS, ids=lambda f: " ".join(f) or "plain")
@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_canary_never_leaks_on_success(canary_profile, cli, fc, command, flags):
    result = cli(*command, *flags)
    assert result.code == 0, result.err
    assert CANARY_KEY not in result.out + result.err
    assert CANARY_SECRET not in result.out + result.err


# --- 6.2: allowlist walk --------------------------------------------------------------

WALK = COMMANDS + [
    ["site", "list", "--status", "update-available"],
    ["site", "list", "--team", "ACME Corp"],
    ["bench", "list", "--team", "team-beta"],
    ["profile", "list"],
]


def test_walk_covers_every_command():
    import typer

    root = typer.main.get_command(app)
    ctx = typer.Context(root)
    walked = {(c[0], c[1]) for c in WALK} | {("profile", "add"), ("profile", "remove")}
    for noun in NOUNS:
        group = root.get_command(ctx, noun)
        for verb in group.list_commands(typer.Context(group)):
            assert (noun, verb) in walked, f"fcm {noun} {verb} is not in the allowlist walk"


@pytest.mark.parametrize("command", WALK, ids=" ".join)
def test_every_command_uses_only_allowlisted_methods(env, cli, strict_fc, command):
    save_profile("work")
    result = cli(*command)
    assert result.code == 0, result.err
    assert set(strict_fc.calls) <= READ_ONLY_METHODS


def test_strict_router_fails_on_a_method_off_the_allowlist(env, strict_fc):
    """Guard for the guard: the strict router itself rejects an unlisted method."""
    with pytest.raises(respx.models.AllMockedAssertionError):
        httpx.get(f"{BASE}/api/method/press.api.bench.deploy")
