"""Inventory service: teams, benches and sites across teams.

This layer has no CLI dependency, so the TUI can reuse it. It never prompts.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any, Generic, TypeVar

from fc_manager.api.client import FCClient
from fc_manager.errors import FcmError, NotFound

MAX_WORKERS = 8

T = TypeVar("T")

SITE_STATUS_FILTERS = {
    "active": "Active",
    "inactive": "Inactive",
    "broken": "Broken",
    "trial": "Trial",
    "update-available": "Update Available",
}


# --- data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Team:
    name: str
    title: str
    owner: str = ""
    label: str = ""  # set by assign_labels(); see `display`

    @property
    def display(self) -> str:
        """What output shows for this team: the label, else the title."""
        return self.label or self.title or self.name


@dataclass(frozen=True)
class Bench:
    team: Team
    name: str
    title: str
    version: str
    status: str
    sites: int
    apps: int


@dataclass(frozen=True)
class Site:
    team: Team
    name: str
    bench: str
    bench_title: str
    status: str
    version: str
    region: str
    update_available: bool


@dataclass(frozen=True)
class App:
    name: str
    title: str
    branch: str
    repository: str
    hash: str


@dataclass(frozen=True)
class SiteDetail:
    site: Site
    server: str
    version: str
    apps: list[App]


@dataclass
class Account:
    user: str
    teams: list[Team]


@dataclass
class Fanout(Generic[T]):
    rows: list[T] = field(default_factory=list)
    failures: list[tuple[Team, FcmError]] = field(default_factory=list)


# --- parsing --------------------------------------------------------------------------


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_teams(raw: Any) -> list[Team]:
    """`account.get` `teams`: dicts with name/team_title, or plain name strings."""
    teams: list[Team] = []
    seen: set[str] = set()
    for entry in raw or []:
        if isinstance(entry, str):
            team = Team(name=entry, title=entry)
        elif isinstance(entry, dict) and entry.get("name"):
            team = Team(
                name=str(entry["name"]),
                title=_str(entry.get("team_title")) or entry["name"],
                owner=_str(entry.get("user")),
            )
        else:
            continue
        if team.name not in seen:
            seen.add(team.name)
            teams.append(team)
    return teams


def assign_labels(teams: list[Team]) -> list[Team]:
    """Label = title when unique; else owner email; else FC name.

    FC gives many teams the default title "Parent Team", so a title alone often does
    not tell teams apart."""
    counts: dict[str, int] = {}
    for team in teams:
        key = team.title.casefold()
        counts[key] = counts.get(key, 0) + 1
    labelled = []
    for team in teams:
        shared = counts[team.title.casefold()] > 1
        label = (team.owner or team.name) if shared else team.title
        labelled.append(replace(team, label=label))
    return labelled


def parse_user(raw: Any) -> str:
    if isinstance(raw, dict):
        return _str(raw.get("email") or raw.get("name"))
    return _str(raw)


def parse_bench(row: dict, team: Team) -> Bench:
    return Bench(
        team=team,
        name=_str(row.get("name")),
        title=_str(row.get("title")),
        version=_str(row.get("version")),
        status=_str(row.get("status")),
        sites=_int(row.get("number_of_sites")),
        apps=_int(row.get("number_of_apps")),
    )


def parse_site(row: dict, team: Team) -> Site:
    region = row.get("server_region_info") or {}
    return Site(
        team=team,
        name=_str(row.get("name")),
        bench=_str(row.get("group")),
        bench_title=_str(row.get("title")),
        status=_str(row.get("status")),
        version=_str(row.get("version")),
        region=_str(region.get("title") if isinstance(region, dict) else region)
        or _str(row.get("cluster")),
        update_available=bool(row.get("update_available")),
    )


def parse_app(row: dict) -> App:
    return App(
        name=_str(row.get("app") or row.get("name")),
        title=_str(row.get("app_title") or row.get("title")),
        branch=_str(row.get("branch")),
        repository=_str(row.get("repository_url") or row.get("repository")),
        hash=_str(row.get("hash"))[:12],
    )


# --- target resolution ----------------------------------------------------------------


@dataclass(frozen=True)
class Resolved(Generic[T]):
    item: T


@dataclass(frozen=True)
class Ambiguous(Generic[T]):
    candidates: list[T]


@dataclass(frozen=True)
class Missing(Generic[T]):
    close_matches: list[T]


def resolve(
    items: Sequence[T],
    query: str,
    *,
    name: Callable[[T], str],
    title: Callable[[T], str],
    alias: Callable[[T], str] | None = None,
) -> Resolved[T] | Ambiguous[T] | Missing[T]:
    """Exact name, then case-insensitive alias (team owner email), then case-insensitive
    title. One match resolves; more than one is ambiguous."""
    by_name = [item for item in items if name(item) == query]
    if len(by_name) == 1:
        return Resolved(by_name[0])
    if len(by_name) > 1:
        return Ambiguous(by_name)

    folded = query.casefold()
    if alias is not None:
        by_alias = [item for item in items if alias(item) and alias(item).casefold() == folded]
        if len(by_alias) == 1:
            return Resolved(by_alias[0])
        if len(by_alias) > 1:
            return Ambiguous(by_alias)

    by_title = [item for item in items if title(item).casefold() == folded]
    if len(by_title) == 1:
        return Resolved(by_title[0])
    if len(by_title) > 1:
        return Ambiguous(by_title)

    keys: dict[str, list[T]] = {}
    for item in items:
        for key in {name(item), title(item)}:
            if key:
                keys.setdefault(key.casefold(), []).append(item)
    close: list[T] = []
    for key in difflib.get_close_matches(folded, list(keys), n=5, cutoff=0.5):
        for item in keys[key]:
            if item not in close:
                close.append(item)
    return Missing(close[:5])


# --- service --------------------------------------------------------------------------


class Inventory:
    def __init__(self, client: FCClient, *, max_workers: int = MAX_WORKERS) -> None:
        self.client = client
        self.max_workers = max_workers
        self._account: Account | None = None

    def account(self) -> Account:
        if self._account is None:
            data = self.client.call("press.api.account.get") or {}
            self._account = Account(
                user=parse_user(data.get("user")),
                teams=assign_labels(parse_teams(data.get("teams"))),
            )
        return self._account

    def teams(self) -> list[Team]:
        return self.account().teams

    def _fanout(self, teams: Iterable[Team], fetch: Callable[[Team], list[T]]) -> Fanout[T]:
        teams = list(teams)
        result: Fanout[T] = Fanout()
        if not teams:
            return result
        workers = max(1, min(self.max_workers, len(teams)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [(team, pool.submit(fetch, team)) for team in teams]
            for team, future in futures:
                try:
                    result.rows.extend(future.result())
                except FcmError as err:
                    result.failures.append((team, err))
        return result

    def benches(self, teams: Iterable[Team]) -> Fanout[Bench]:
        def fetch(team: Team) -> list[Bench]:
            rows = self.client.call("press.api.bench.all", team=team.name) or []
            return [parse_bench(row, team) for row in rows if isinstance(row, dict)]

        result = self._fanout(teams, fetch)
        # bench.all includes child teams, so one bench can come back under 2 teams.
        # Keep the first one, in team discovery order.
        seen: set[str] = set()
        unique = []
        for bench in result.rows:
            if bench.name not in seen:
                seen.add(bench.name)
                unique.append(bench)
        result.rows = unique
        return result

    def sites(self, teams: Iterable[Team], status: str | None = None) -> Fanout[Site]:
        site_filter = {"status": SITE_STATUS_FILTERS[status], "tag": ""} if status else None
        known = {team.name: team for team in self.teams()}

        def fetch(team: Team) -> list[Site]:
            rows = self.client.call("press.api.site.all", team=team.name, site_filter=site_filter)
            sites = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                owner = known.get(_str(row.get("team")), team)
                sites.append(parse_site(row, owner))
            return sites

        result = self._fanout(teams, fetch)
        seen: set[str] = set()
        unique = []
        for site in result.rows:
            if site.name not in seen:
                seen.add(site.name)
                unique.append(site)
        result.rows = unique
        return result

    def site_detail(self, site: Site) -> SiteDetail:
        team = site.team.name
        data = self.client.call("press.api.site.get", team=team, name=site.name)
        if not isinstance(data, dict):
            raise NotFound(f"Site {site.name} not found", target=f"team {team}")
        apps = self.client.call("press.api.site.installed_apps", team=team, name=site.name) or []
        return SiteDetail(
            site=site,
            server=_str(data.get("server")),
            version=_str(data.get("frappe_version")) or site.version,
            apps=[parse_app(row) for row in apps if isinstance(row, dict)],
        )
