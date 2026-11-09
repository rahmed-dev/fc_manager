from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import keyring
import pytest
import respx
from keyring.backend import KeyringBackend

from fc_manager import config, credentials, redact
from fc_manager.cli import picker
from fc_manager.cli.app import run
from fc_manager.redact import Credentials

FIXTURES = Path(__file__).parent / "fixtures" / "fc"
BASE = "https://cloud.frappe.io"

KEY = "key-1111aaaa"
SECRET = "secret-2222bbbb"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def method_url(method: str) -> str:
    return f"{BASE}/api/method/{method}"


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError("missing")
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def _clean_redaction_registry():
    redact.clear()
    yield
    redact.clear()


@pytest.fixture
def memkeyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def env(tmp_path, monkeypatch, memkeyring):
    """Isolated config dir, empty keyring, no FCM_* variables, not interactive."""
    monkeypatch.setenv(config.CONFIG_DIR_ENV, str(tmp_path / "cfg"))
    for name in (credentials.ENV_KEY, credentials.ENV_SECRET, credentials.ENV_PROFILE):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: False)
    return tmp_path


def save_profile(name: str = "work", key: str = KEY, secret: str = SECRET, default=True):
    cfg = config.load()
    cfg.profiles[name] = config.Profile(name=name, base_url=BASE)
    if default or not cfg.default_profile:
        cfg.default_profile = name
    config.save(cfg)
    credentials.store(name, Credentials(key, secret))


@dataclass
class Result:
    code: int
    out: str
    err: str


@pytest.fixture
def cli(capsys):
    def invoke(*args: str) -> Result:
        code = run(list(args))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return invoke


TEAMS = [
    {"name": "team-own", "team_title": "Own Team", "user": "owner@example.com"},
    {"name": "team-acme", "team_title": "ACME Corp", "user": "acme@example.com"},
    {"name": "team-beta", "team_title": "Beta Ltd", "user": "beta@example.com"},
]


def _bench(name, title, sites=1):
    return {
        "name": name,
        "title": title,
        "version": "Version 15",
        "status": "Active",
        "number_of_sites": sites,
        "number_of_apps": 3,
        "tags": [],
    }


def _site(name, team, group, title, status="Active", update=False):
    row = {
        "name": name,
        "host_name": name,
        "status": status,
        "bench": f"{group}-000001-f1",
        "group": group,
        "title": title,
        "version": "Version 15",
        "team": team,
        "server_region_info": {"title": "Mumbai", "image": ""},
        "tags": [],
    }
    if update:
        row["update_available"] = True
    return row


@dataclass
class FakeFC:
    """A respx-backed FC: per-team benches and sites, chosen by X-Press-Team."""

    teams: list = field(default_factory=lambda: copy.deepcopy(TEAMS))
    benches: dict = field(default_factory=dict)
    sites: dict = field(default_factory=dict)
    team_errors: dict = field(default_factory=dict)  # team -> (status, body)
    account_error: tuple | None = None
    calls: list = field(default_factory=list)

    def _team_error(self, request):
        team = request.headers.get("X-Press-Team")
        if team in self.team_errors:
            status, body = self.team_errors[team]
            return team, httpx.Response(status, json=body)
        return team, None

    def handle(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(method)
        if method == "press.api.account.get":
            if self.account_error:
                status, body = self.account_error
                return httpx.Response(status, json=body)
            return httpx.Response(
                200,
                json={"message": {"user": {"email": "owner@example.com"}, "teams": self.teams}},
            )
        team, error = self._team_error(request)
        if error is not None:
            return error
        if method == "press.api.bench.all":
            return httpx.Response(200, json={"message": self.benches.get(team, [])})
        if method == "press.api.site.all":
            rows = self.sites.get(team, [])
            raw = request.url.params.get("site_filter")
            if raw:
                wanted = json.loads(raw)["status"]
                if wanted == "Update Available":
                    rows = [r for r in rows if r.get("update_available")]
                else:
                    rows = [r for r in rows if r["status"] == wanted]
            return httpx.Response(200, json={"message": rows})
        if method == "press.api.site.get":
            name = request.url.params["name"]
            for rows in self.sites.values():
                for row in rows:
                    if row["name"] == name:
                        return httpx.Response(
                            200,
                            json={
                                "message": {
                                    "name": name,
                                    "frappe_version": "Version 15",
                                    "server": "f1-mumbai.example.com",
                                }
                            },
                        )
            return httpx.Response(404, json=fixture("error_not_found.json"))
        if method == "press.api.site.installed_apps":
            return httpx.Response(200, json=fixture("site_installed_apps.json"))
        return httpx.Response(500, json={"message": f"fake FC has no {method}"})


def default_fake() -> FakeFC:
    fake = FakeFC()
    fake.benches = {
        "team-own": [_bench("bench-0001", "Own Bench")],
        "team-acme": [_bench("bench-1234", "ACME Prod", 2), _bench("bench-1240", "Prod")],
        "team-beta": [_bench("bench-0981", "Prod")],
    }
    fake.sites = {
        "team-own": [_site("own.example.com", "team-own", "bench-0001", "Own Bench")],
        "team-acme": [
            _site("erp.acme.example.com", "team-acme", "bench-1234", "ACME Prod", update=True),
            _site("hr.acme.example.com", "team-acme", "bench-1234", "ACME Prod", "Inactive"),
            _site("stage.acme.example.com", "team-acme", "bench-1240", "Prod"),
        ],
        "team-beta": [_site("erp.beta.example.com", "team-beta", "bench-0981", "Prod")],
    }
    return fake


@pytest.fixture
def fc():
    fake = default_fake()
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.route().mock(side_effect=fake.handle)
        yield fake


@pytest.fixture
def strict_fc():
    """Like `fc`, but fails the test on a request outside the read-only allowlist."""
    from fc_manager.api.client import READ_ONLY_METHODS

    fake = default_fake()
    with respx.mock(base_url=BASE, assert_all_called=False, assert_all_mocked=True) as router:
        for method in READ_ONLY_METHODS:
            router.get(f"/api/method/{method}").mock(side_effect=fake.handle)
        yield fake
