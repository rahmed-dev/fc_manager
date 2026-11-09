"""App service: add a marketplace app to a bench group, and install an app on a site.

This layer has no CLI dependency. It never prompts. Every FC request goes to the team of
the bench or the site only. The only writes are `add_market()`, `add_github()` and
`install()`.

FC facts (press source, `frappe/press` master, and spike question 6 of 2026-11-09):
- `press.api.bench.all_apps` lists the published marketplace apps that the bench group does
  not have. `sources` holds the public sources for the Frappe version of the group; an
  empty list means that the app is not compatible with that version.
- `press.api.bench.add_apps` saves a list of marketplace apps in the group, in one request.
  A GitHub app goes through `press.api.client.run_doc_method` (Release Group, add_app),
  one app per request. Neither starts a job. The apps reach the benches at the next deploy.
- FC has no marketplace search that works over GET, so the app list is read once per bench
  and session and searched locally (fc_manager.search).
- `press.api.github.options` lists the GitHub installations of the team and their repos;
  `github.branches` the branches of a repo; `github.app` the app name, title and Frappe
  version range of a branch (spike question 7, 2026-11-09).
- `press.api.site.available_apps` lists the apps on the bench of the site that the site
  does not have. A marketplace app can have `plans`. fcm never sends a plan, so an app with
  plans is not offered (decision by Riz, 2026-11-09).
- `press.api.site.install_app` returns nothing. FC starts an "Install App on Site" job,
  which the watch finds through the running jobs of the site, as for a migrate.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from fc_manager.api.client import FCClient
from fc_manager.deploy import DeployService
from fc_manager.errors import InstallFailed, InstallUnknown, UsageError
from fc_manager.inventory import Bench, Site
from fc_manager.migrate import (
    IN_PROGRESS,
    POLL_SECONDS,
    MigrateService,
    MigrateState,
    watch_site_job,
)
from fc_manager.search import SearchIndex

ADD_METHOD = "press.api.bench.add_apps"
GITHUB_ADD_METHOD = "press.api.client.run_doc_method"
GITHUB_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
INSTALL_METHOD = "press.api.site.install_app"
INSTALL_JOB_TYPE = "Install App on Site"
# FC installs an app only on an Active site (press Site.install_app, @site_action).
INSTALL_STATUSES = ("Active",)
PLANS_NOTE = "has plans: install it from the FC dashboard"


def _str(value: Any) -> str:
    return "" if value is None else str(value)


# --- data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class AppSource:
    name: str
    branch: str
    repository: str  # owner/repository


@dataclass(frozen=True)
class MarketApp:
    """One app that FC offers for a bench group."""

    app: str
    title: str
    sources: tuple[AppSource, ...]

    @property
    def compatible(self) -> bool:
        return bool(self.sources)


@dataclass(frozen=True)
class AddPlan:
    """Marketplace apps to add in one `add_apps` request: (app, source) pairs."""

    bench: Bench
    picks: tuple[tuple[MarketApp, AppSource], ...]

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.bench.name,
            "apps": [{"app": app.app, "source": source.name} for app, source in self.picks],
        }


@dataclass(frozen=True)
class GitHubRepo:
    owner: str
    name: str
    installation: str | None = None  # FC GitHub installation id; None for a public URL
    default_branch: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


@dataclass(frozen=True)
class GitHubApp:
    name: str
    title: str
    frappe_version: str


@dataclass(frozen=True)
class GitHubPlan:
    """One GitHub app to add through run_doc_method (Release Group, add_app)."""

    bench: Bench
    repo: GitHubRepo
    branch: str
    app: GitHubApp

    def payload(self) -> dict[str, Any]:
        app: dict[str, Any] = {
            "name": self.app.name,
            "title": self.app.title,
            "repository_url": self.repo.url,
            "branch": self.branch,
        }
        if self.repo.installation:
            app["github_installation_id"] = self.repo.installation
        return {"dt": "Release Group", "dn": self.bench.name, "method": "add_app",
                "args": {"app": app}}  # fmt: skip


@dataclass(frozen=True)
class SiteApp:
    """One app that FC offers for a site: on the bench of the site, not on the site."""

    app: str
    title: str
    branch: str
    source: str
    repository: str
    has_plans: bool

    @property
    def pickable(self) -> bool:
        return not self.has_plans


@dataclass(frozen=True)
class SiteCheck:
    site: Site
    status: str  # the site status on FC at the check


@dataclass(frozen=True)
class InstallPlan:
    site: Site
    status: str
    app: SiteApp

    def payload(self) -> dict[str, Any]:
        # Never a plan: see the module note.
        return {"name": self.site.name, "app": self.app.app}


# --- parsers --------------------------------------------------------------------------


def _repository(row: dict) -> str:
    owner, repo = _str(row.get("repository_owner")), _str(row.get("repository"))
    if owner and repo:
        return f"{owner}/{repo}"
    url = _str(row.get("repository_url"))
    if url:
        path = urlparse(url if "://" in url else f"https://{url}").path.strip("/")
        return path.removesuffix(".git") or url
    return repo or owner


def _title(row: dict) -> str:
    return _str(row.get("title")) or _str(row.get("app_title")) or _str(row.get("app"))


def parse_all_apps(data: Any) -> list[MarketApp]:
    rows = data if isinstance(data, list) else []
    apps = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("app"):
            continue
        sources = tuple(
            AppSource(
                name=_str(s.get("name")), branch=_str(s.get("branch")), repository=_repository(s)
            )
            for s in row.get("sources") or []
            if isinstance(s, dict) and s.get("name")
        )
        apps.append(MarketApp(app=_str(row.get("app")), title=_title(row), sources=sources))
    return apps


def parse_available_apps(data: Any) -> list[SiteApp]:
    rows = data if isinstance(data, list) else []
    return [
        SiteApp(
            app=_str(row.get("app")),
            title=_title(row),
            branch=_str(row.get("branch")),
            source=_str(row.get("name")),
            repository=_repository(row),
            has_plans=bool(row.get("has_plans_available") or row.get("plans")),
        )
        for row in rows
        if isinstance(row, dict) and row.get("app")
    ]


def parse_github_repos(data: Any) -> list[GitHubRepo]:
    data = data if isinstance(data, dict) else {}
    repos = []
    for inst in data.get("installations") or []:
        if not isinstance(inst, dict):
            continue
        login, inst_id = _str(inst.get("login")), _str(inst.get("id")) or None
        for repo in inst.get("repos") or []:
            if isinstance(repo, dict) and repo.get("name"):
                url = _str(repo.get("url"))
                match = GITHUB_URL.match(url)
                owner = match.group(1) if match else login
                repos.append(GitHubRepo(owner, _str(repo.get("name")), inst_id,
                                        _str(repo.get("default_branch"))))  # fmt: skip
    return sorted(repos, key=lambda r: r.full_name.lower())


def parse_repo_url(url: str) -> GitHubRepo:
    """A public GitHub URL: https://github.com/<owner>/<repo>. Exit 2 for anything else."""
    match = GITHUB_URL.match(url.strip())
    if not match:
        raise UsageError(
            f"Not a GitHub repository URL: {url}",
            hint="Use the form https://github.com/<owner>/<repo>.",
        )
    return GitHubRepo(match.group(1), match.group(2))


def order_branches(names: list[str], default: str = "") -> list[str]:
    """The default branch first, then version-* branches, then the rest by name."""
    unique = list(dict.fromkeys(n for n in names if n))
    return sorted(
        unique,
        key=lambda n: (n != default, not n.startswith("version-"), n),
    )


# --- service --------------------------------------------------------------------------


class AppService:
    """One service per session: it keeps the marketplace list of each bench and the GitHub
    repos of each team, so that a second add on the same bench reads nothing again."""

    def __init__(self, client: FCClient) -> None:
        self.client = client
        self.jobs = MigrateService(client)  # site status, running jobs, job reads
        self._market: dict[str, list[MarketApp]] = {}
        self._index: dict[str, SearchIndex[MarketApp]] = {}
        self._repos: dict[str, list[GitHubRepo]] = {}

    # marketplace -----------------------------------------------------------------------

    def offered_apps(self, bench: Bench) -> list[MarketApp]:
        """The marketplace apps of the group (compatible first). Read once per bench."""
        if bench.name not in self._market:
            data = self.client.call(
                "press.api.bench.all_apps", team=bench.team.name, name=bench.name
            )
            apps = sorted(parse_all_apps(data), key=lambda a: (not a.compatible, a.title.lower()))
            self._market[bench.name] = apps
        return self._market[bench.name]

    def search_index(self, bench: Bench) -> SearchIndex[MarketApp]:
        """The search index of the compatible apps of the group. Built once per bench."""
        if bench.name not in self._index:
            compatible = [a for a in self.offered_apps(bench) if a.compatible]
            self._index[bench.name] = SearchIndex(compatible, key=lambda a: a.app,
                                                  title=lambda a: a.title)  # fmt: skip
        return self._index[bench.name]

    @staticmethod
    def pick_app(bench: Bench, apps: list[MarketApp], name: str) -> MarketApp:
        """The app named by `--app`. Exit 2 when FC does not offer it or it is not
        compatible."""
        target = f"bench {bench.title or bench.name}"
        found = next((a for a in apps if a.app == name), None)
        if found is None:
            raise UsageError(
                f"FC does not offer app {name} for bench {bench.title or bench.name}",
                target=target,
                hint=f"The bench group may have it already. Run: fcm bench-show {bench.name}",
            )
        if not found.compatible:
            raise UsageError(
                f"App {name} has no release for {bench.version or 'the Frappe version'} "
                f"of bench {bench.title or bench.name}",
                target=target,
            )
        return found

    @staticmethod
    def pick_source(bench: Bench, app: MarketApp, name: str | None) -> AppSource | None:
        """The source to add. One source: that one. `name` set: that one, else exit 2.
        Several and no `name`: None (the caller asks, or fails in a script)."""
        if name:
            found = next((s for s in app.sources if s.name == name), None)
            if found is None:
                raise UsageError(
                    f"App {app.app} has no source {name} for bench {bench.title or bench.name}",
                    target=f"bench {bench.title or bench.name}",
                    hint="Sources: " + sources_text(app),
                )
            return found
        return app.sources[0] if len(app.sources) == 1 else None

    def add_market(self, plan: AddPlan) -> None:
        """Bench write: add the marketplace apps in one request. FC starts no job."""
        self.client.write(ADD_METHOD, team=plan.bench.team.name, **plan.payload())

    # GitHub ----------------------------------------------------------------------------

    def github_repos(self, bench: Bench) -> list[GitHubRepo]:
        """The repos of the FC GitHub installations of the team. Read once per team."""
        team = bench.team.name
        if team not in self._repos:
            self._repos[team] = parse_github_repos(
                self.client.call("press.api.github.options", team=team)
            )
        return self._repos[team]

    def github_branches(self, bench: Bench, repo: GitHubRepo) -> list[str]:
        params: dict[str, Any] = {"owner": repo.owner, "name": repo.name}
        if repo.installation:
            params["installation"] = repo.installation
        data = self.client.call("press.api.github.branches", team=bench.team.name, **params)
        rows = data if isinstance(data, list) else []
        names = [_str(r.get("name")) for r in rows if isinstance(r, dict)]
        return order_branches(names, repo.default_branch)

    def github_app(self, bench: Bench, repo: GitHubRepo, branch: str) -> GitHubApp:
        """The app of a branch, as FC reads it from hooks.py. Exit 2 when the bench group
        has an app with that name already."""
        params: dict[str, Any] = {"owner": repo.owner, "repository": repo.name, "branch": branch}
        if repo.installation:
            params["installation"] = repo.installation
        data = self.client.call("press.api.github.app", team=bench.team.name, **params)
        data = data if isinstance(data, dict) else {}
        app = GitHubApp(
            name=_str(data.get("name")),
            title=_str(data.get("title")) or _str(data.get("name")),
            frappe_version=_str(data.get("frappe_version")),
        )
        if not app.name:
            raise UsageError(
                f"FC found no Frappe app in {repo.full_name} branch {branch}",
                target=f"bench {bench.title or bench.name}",
            )
        on_bench = {a.app for a in DeployService(self.client).info(bench).apps}
        if app.name in on_bench:
            raise UsageError(
                f"Bench {bench.title or bench.name} already has app {app.name}",
                target=f"bench {bench.title or bench.name}",
                hint=f"Run: fcm bench-show {bench.name}",
            )
        return app

    def add_github(self, plan: GitHubPlan) -> None:
        """Bench write: add one GitHub app through run_doc_method. FC starts no job."""
        self.client.write(GITHUB_ADD_METHOD, team=plan.bench.team.name, **plan.payload())

    # site ------------------------------------------------------------------------------

    def check_site(self, site: Site) -> SiteCheck:
        """Refuse a site that is not Active, or that has a job in progress."""
        status = self.jobs.site_status(site)
        if status not in INSTALL_STATUSES:
            raise UsageError(
                f"FC installs an app only on an Active site: {site.name} is "
                f"{status or 'in an unknown status'}",
                target=f"site {site.name}",
            )
        busy = [j for j in self.jobs.running_jobs(site) if j.status in IN_PROGRESS]
        if busy:
            job = busy[0]
            raise UsageError(
                f"FC has a {job.job_type} job in the {job.status} state on site {site.name}",
                target=f"site {site.name}",
                hint=f"Wait until it ends. Run: fcm site-show {site.name}",
            )
        return SiteCheck(site=site, status=status)

    def offered_site_apps(self, site: Site) -> list[SiteApp]:
        data = self.client.call(
            "press.api.site.available_apps", team=site.team.name, name=site.name
        )
        return sorted(parse_available_apps(data), key=lambda a: (not a.pickable, a.title.lower()))

    @staticmethod
    def pick_site_app(site: Site, apps: list[SiteApp], name: str) -> SiteApp:
        """The app named by `--app`. Exit 2 when FC does not offer it, or when it has
        plans."""
        found = next((a for a in apps if a.app == name), None)
        if found is None:
            raise UsageError(
                f"App {name} is not on the bench of site {site.name}, or the site has it already",
                target=f"site {site.name}",
                hint=f"To add it to the bench first, run: fcm bench-add-app {site.bench}",
            )
        if not found.pickable:
            raise UsageError(
                f"App {name} has marketplace plans. fcm does not choose a plan.",
                target=f"site {site.name}",
                hint=f"Install {name} from the FC dashboard.",
            )
        return found

    def install(self, plan: InstallPlan) -> None:
        """The only site write: send the install. FC returns nothing."""
        self.client.write(INSTALL_METHOD, team=plan.site.team.name, **plan.payload())

    def watch_install(
        self,
        plan: InstallPlan,
        sleep: Callable[[float], None],
        poll_seconds: float = POLL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> Iterator[MigrateState]:
        return watch_site_job(
            self.jobs,
            plan.site,
            job_type=INSTALL_JOB_TYPE,
            word="install",
            unknown=InstallUnknown,
            failed=InstallFailed,
            sleep=sleep,
            poll_seconds=poll_seconds,
            clock=clock,
        )


def sources_text(app: MarketApp) -> str:
    return ", ".join(f"{s.name} ({s.branch}, {s.repository})" for s in app.sources)
