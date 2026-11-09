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
from fc_manager.api.client import READ_ONLY_METHODS, WRITE_METHODS
from fc_manager.cli.app import app
from fc_manager.inventory import Inventory

from .conftest import BASE, default_fake, fixture, save_profile

CANARY_KEY = "canaryKEY-7f3a9c"
CANARY_SECRET = "canarySECRET-91be4d"

COMMANDS = [
    ["team-list"],
    ["bench-list"],
    ["site-list"],
    ["site-list", "--bench", "ACME Prod"],
    ["site-show", "erp.acme.example.com"],
    ["profile-test", "work"],
    ["bench-show", "bench-1234"],
    ["bench-deploy", "bench-1234", "--all-apps", "--dry-run"],
    ["site-migrate", "erp.acme.example.com", "--dry-run"],
    ["site-update", "erp.acme.example.com", "--dry-run"],
    ["bench-add-app", "bench-1234", "--app", "crm", "--dry-run"],
    ["site-install-app", "erp.acme.example.com", "--app", "crm", "--dry-run"],
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
    ["site-list", "--status", "update-available"],
    ["site-list", "--team", "ACME Corp"],
    ["bench-list", "--team", "team-beta"],
    ["profile-list"],
    ["bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234", "--no-wait"],
    ["site-migrate", "erp.acme.example.com", "--confirm", "erp.acme.example.com", "--no-wait"],
    ["site-update", "erp.acme.example.com", "--confirm", "erp.acme.example.com", "--no-wait"],
    ["bench-add-app", "bench-1234", "--app", "crm", "--confirm", "bench-1234"],
    ["site-install-app", "erp.acme.example.com", "--app", "crm",
     "--confirm", "erp.acme.example.com", "--no-wait"],
    ["bench-add-app", "bench-1234", "--repo", "https://github.com/acme/tools",
     "--branch", "main", "--confirm", "bench-1234"],
]  # fmt: skip

DEPLOY = "press.api.bench.deploy_and_update"
MIGRATE = "press.api.site.migrate"
UPDATE = "press.api.site.update"
ADD_APP = "press.api.bench.add_apps"
INSTALL = "press.api.site.install_app"
# Each write command and the one write method it may send.
OWN_WRITE = {
    "bench-deploy": DEPLOY,
    "site-migrate": MIGRATE,
    "site-update": UPDATE,
    "bench-add-app": ADD_APP,
    "site-install-app": INSTALL,
}


def posts(fake) -> list[str]:
    return [method for method, _, verb in fake.teams_seen if verb == "POST"]


def expected_posts(command: list[str]) -> list[str]:
    """The POSTs a command may send: its own write method once, or none for a dry run.
    A GitHub add (--repo) sends run_doc_method instead of add_apps."""
    if "--dry-run" in command or command[0] not in OWN_WRITE:
        return []
    if command[0] == "bench-add-app" and "--repo" in command:
        return ["press.api.client.run_doc_method"]
    return [OWN_WRITE[command[0]]]


def test_walk_covers_every_command():
    import typer

    root = typer.main.get_command(app)
    ctx = typer.Context(root)
    walked = {c[0] for c in WALK} | {"profile-add", "profile-remove"}
    for name in root.list_commands(ctx):
        assert name in walked, f"fcm {name} is not in the allowlist walk"


@pytest.mark.parametrize("command", WALK, ids=" ".join)
def test_every_command_uses_only_allowlisted_methods(env, cli, strict_fc, command):
    save_profile("work")
    result = cli(*command)
    assert result.code == 0, result.err
    assert set(strict_fc.calls) <= READ_ONLY_METHODS | WRITE_METHODS
    # Only a write command (not a dry run) sends a POST, and only its own write method.
    assert posts(strict_fc) == expected_posts(command)


def test_walk_detects_a_post_from_another_command(env, cli, strict_fc, monkeypatch):
    """Guard for the guard: a read command that sent a write would fail the walk."""
    save_profile("work")

    def benches_that_write(self, teams):
        self.client.write(DEPLOY, team="team-acme", name="bench-1234", apps=[], sites=[])
        raise AssertionError("unreachable")

    monkeypatch.setattr(Inventory, "benches", benches_that_write)
    cli("bench-list")
    assert posts(strict_fc) == [DEPLOY]
    assert posts(strict_fc) != expected_posts(["bench-list"])


def test_walk_detects_the_wrong_write_from_site_migrate(env, cli, strict_fc, monkeypatch):
    """Guard for the guard: site-migrate that sent the deploy method would fail the walk."""
    from fc_manager import migrate

    save_profile("work")
    monkeypatch.setattr(migrate, "MIGRATE_METHOD", DEPLOY)
    command = next(c for c in WALK if c[0] == "site-migrate" and "--confirm" in c)
    cli(*command)
    assert posts(strict_fc) == [DEPLOY]
    assert posts(strict_fc) != expected_posts(command)


def test_walk_detects_the_wrong_write_from_site_update(env, cli, strict_fc, monkeypatch):
    """Guard for the guard: site-update that sent the migrate method would fail the walk."""
    from fc_manager import update

    save_profile("work")
    monkeypatch.setattr(update, "UPDATE_METHOD", MIGRATE)
    command = next(c for c in WALK if c[0] == "site-update" and "--confirm" in c)
    cli(*command)
    assert posts(strict_fc) == [MIGRATE]
    assert posts(strict_fc) != expected_posts(command)


@pytest.mark.parametrize(
    ("command_name", "attribute", "wrong"),
    [
        ("bench-add-app", "ADD_METHOD", DEPLOY),
        ("site-install-app", "INSTALL_METHOD", MIGRATE),
    ],
)
def test_walk_detects_the_wrong_write_from_app_commands(
    env, cli, strict_fc, monkeypatch, command_name, attribute, wrong
):
    """Guard for the guard: an app command that sent another write would fail the walk."""
    from fc_manager import apps

    save_profile("work")
    monkeypatch.setattr(apps, attribute, wrong)
    command = next(c for c in WALK if c[0] == command_name and "--confirm" in c)
    cli(*command)
    assert posts(strict_fc) == [wrong]
    assert posts(strict_fc) != expected_posts(command)


def test_strict_router_fails_on_a_method_off_the_allowlist(env, strict_fc):
    """Guard for the guard: the strict router itself rejects an unlisted method."""
    with pytest.raises(respx.models.AllMockedAssertionError):
        httpx.get(f"{BASE}/api/method/press.api.bench.deploy")


# --- deploy 2.4, migrate 5.3, update 5.3: the write path never leaks the canary ---------

WRITE_ERRORS = {
    "server": lambda r: httpx.Response(502, text=_echo_headers(r)),
    "timeout": lambda r: (_ for _ in ()).throw(httpx.ReadTimeout(f"t {r.headers}", request=r)),
    "validation": lambda r: httpx.Response(
        417, json={"exc_type": "ValidationError", "exception": f"bad {r.headers}"}
    ),
    "permission": lambda r: httpx.Response(403, json=fixture("error_permission.json")),
}


WRITE_COMMANDS = [
    ["bench-deploy", "bench-1234", "--all-apps", "--confirm", "bench-1234"],
    ["site-migrate", "erp.acme.example.com", "--confirm", "erp.acme.example.com"],
    ["site-update", "erp.acme.example.com", "--confirm", "erp.acme.example.com"],
    ["bench-add-app", "bench-1234", "--app", "crm", "--confirm", "bench-1234"],
    ["site-install-app", "erp.acme.example.com", "--app", "crm", "--confirm",
     "erp.acme.example.com"],
]  # fmt: skip


@pytest.mark.parametrize("path", sorted(WRITE_ERRORS))
@pytest.mark.parametrize("flags", FLAGS, ids=lambda f: " ".join(f) or "plain")
@pytest.mark.parametrize("command", WRITE_COMMANDS, ids=lambda c: c[0])
def test_canary_never_leaks_on_write_errors(canary_profile, cli, command, flags, path):
    fake = default_fake()

    def handler(request):
        if request.method == "POST":
            fake.posts.append(request.url.path)
            return WRITE_ERRORS[path](request)
        return fake.handle(request)

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.route().mock(side_effect=handler)
        result = cli(*command, *flags)
    assert result.code != 0
    assert len(fake.posts) == 1  # never retried
    for stream in (result.out, result.err):
        assert CANARY_KEY not in stream
        assert CANARY_SECRET not in stream
