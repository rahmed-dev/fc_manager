"""`fcm bench-add-app` and `fcm site-install-app`.

bench-add-app: bench (or team, bench on a terminal), app, source, preview, typed bench
title, add request, result. FC starts no job for an add; the app reaches the benches at
the next deploy. The only write is the add request.

site-install-app: site (or team, bench, site on a terminal), checks, app, preview, typed
site name, install request, job watch, result. The only write is the install request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated

import typer
from rich.live import Live

from fc_manager.apps import (
    PLANS_NOTE,
    AddPlan,
    AppService,
    AppSource,
    GitHubPlan,
    InstallPlan,
    MarketApp,
    SiteApp,
    parse_repo_url,
    sources_text,
)
from fc_manager.cli import picker
from fc_manager.cli.common import (
    DebugOpt,
    JsonOpt,
    ProfileOpt,
    Session,
    TeamOpt,
    explain_team_error,
    scope_teams,
    session,
    team_label,
)
from fc_manager.cli.deploy import WatchStopped, _pick_bench
from fc_manager.cli.inventory import resolve_site, walk_to_site
from fc_manager.cli.migrate import _state_json
from fc_manager.cli.root import app
from fc_manager.cli.update import UpdateOptions  # noqa: F401 - site-update before us in the help
from fc_manager.cli.watch import WatchView, changes, steps_table
from fc_manager.errors import FcmError, UsageError
from fc_manager.inventory import Bench, Site
from fc_manager.migrate import MigrateState
from fc_manager.search import SearchIndex

INSTALL_STAGE_TEXT = {
    "finding": "FC accepted the install; waiting for its job to show up",
    "waiting": "the install job is queued on FC",
    "running": "FC is installing the app",
    "success": "finished",
    "failure": "failed",
}


@dataclass(frozen=True)
class AddAppOptions:
    apps: tuple[str, ...] = ()  # marketplace app names (--app, repeat); empty: not given
    sources: tuple[tuple[str, str], ...] = ()  # (app, source) from --source app=source
    repo: str | None = None  # GitHub URL (--repo)
    branch: str | None = None
    confirm: str | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class InstallAppOptions:
    app: str | None = None
    confirm: str | None = None
    dry_run: bool = False
    no_wait: bool = False


def _scoped(err: FcmError, team) -> FcmError:
    """Name the team (and its owner for a permission error), unless an item is the target."""
    if err.target and not err.target.startswith("team "):
        return err
    return explain_team_error(err, team)


def _team_json(team) -> dict:
    return {"name": team.name, "label": team.display, "owner": team.owner}


# --- bench-add-app --------------------------------------------------------------------

MARKET, GITHUB, PASTE_URL = "market", "github", "paste"


def app_service(s: Session) -> AppService:
    """One AppService per session, so that the app lists are read once (design D11)."""
    service = s.cache.get("apps")
    if service is None:
        service = s.cache["apps"] = AppService(s.client)
    return service


def _market_label(a: MarketApp) -> str:
    return f"{a.title} ({a.app})"


def _search_market(s: Session, bench: Bench, service: AppService, picked, *, back, path):
    index = service.search_index(bench)
    taken = {a.app for a, _ in picked}

    def find(text: str):
        return [(_market_label(a), a) for a in index.search(text) if a.app not in taken][:10]

    return picker.search(f"Search the marketplace ({len(index)} apps)", find, back=back,
                         path=path)  # fmt: skip


def _choose_source(app_: MarketApp, *, back: bool, path) -> AppSource:
    return picker.choose(
        f"Source of {app_.app}",
        [(f"{x.branch}  {x.repository}  ({x.name})", x) for x in app_.sources],
        back=back,
        path=path,
    )


def _market_picks(s: Session, bench: Bench, opts: AddAppOptions, *, back: bool, path):
    """(app, source) pairs: from --app in a script, else from the search on a terminal."""
    service = app_service(s)
    name = bench.title or bench.name
    sources = dict(opts.sources)
    if opts.apps:
        apps = service.offered_apps(bench)
        chosen = [service.pick_app(bench, apps, app_) for app_ in dict.fromkeys(opts.apps)]
    else:
        if not any(a.compatible for a in service.offered_apps(bench)):
            raise UsageError(f"No marketplace app can be added to bench {name}",
                             target=f"bench {bench.name}")  # fmt: skip
        chosen = []
        while True:
            pairs = [(a, None) for a in chosen]
            chosen.append(_search_market(s, bench, service, pairs, back=back, path=path))
            s.out.message("Picked: " + ", ".join(a.app for a in chosen))
            if not picker.ask_yes_no("Add another app?", default=False):
                break
    picks = []
    for app_ in chosen:
        source = service.pick_source(bench, app_, sources.get(app_.app))
        if source is None:
            if not s.interactive:
                raise UsageError(
                    f"App {app_.app} has {len(app_.sources)} sources for bench {name}",
                    target=f"bench {bench.name}",
                    hint=f"Pick one with --source {app_.app}=<source>. Sources: "
                    + sources_text(app_),
                )
            source = _choose_source(app_, back=back, path=path)
        picks.append((app_, source))
    return AddPlan(bench=bench, picks=tuple(picks))


def _github_plan(s: Session, bench: Bench, opts: AddAppOptions, *, back: bool, path):
    service = app_service(s)
    if opts.repo:
        repo = parse_repo_url(opts.repo)
    else:
        repos = service.github_repos(bench)
        entries: list = [(r.full_name, r) for r in repos]
        entries.append(("Paste a public GitHub URL", PASTE_URL))
        repo = picker.choose("GitHub repository", entries, back=back, path=path)
        if repo == PASTE_URL:
            repo = parse_repo_url(
                picker.ask_text("Public GitHub URL (https://github.com/owner/repo):")
            )
    branches = service.github_branches(bench, repo)
    if opts.branch:
        if opts.branch not in branches:
            raise UsageError(f"Repository {repo.full_name} has no branch {opts.branch}",
                             target=f"bench {bench.name}")  # fmt: skip
        branch = opts.branch
    elif not s.interactive:
        raise UsageError("No branch given", hint="Give the branch: --branch <branch>")
    else:
        index = SearchIndex(branches, key=lambda b: b)

        def find(text: str):
            rows = index.search(text) if text.strip() else branches[:10]
            return [(b, b) for b in rows]

        branch = picker.search(f"Branch of {repo.full_name} ({len(branches)})", find,
                               back=back, path=path)  # fmt: skip
    app_ = service.github_app(bench, repo, branch)
    return GitHubPlan(bench=bench, repo=repo, branch=branch, app=app_)


def _add_plan_json(s: Session, plan: AddPlan | GitHubPlan) -> dict:
    bench = plan.bench
    data = {
        "profile": s.profile.label,
        "team": _team_json(bench.team),
        "bench": {"name": bench.name, "title": bench.title, "version": bench.version},
    }
    if isinstance(plan, AddPlan):
        data["source"] = "marketplace"
        data["apps"] = [
            {"name": a.app, "title": a.title, "source": x.name, "branch": x.branch,
             "repository": x.repository}
            for a, x in plan.picks
        ]  # fmt: skip
    else:
        data["source"] = "github"
        data["apps"] = [{"name": plan.app.name, "title": plan.app.title, "branch": plan.branch,
                         "repository": plan.repo.url,
                         "frappe_version": plan.app.frappe_version}]  # fmt: skip
    return data


def _add_preview(s: Session, plan: AddPlan | GitHubPlan) -> None:
    bench = plan.bench
    fields = [
        ("Profile", s.profile.label),
        ("Team", team_label(bench.team)),
        ("Owner", bench.team.owner or "unknown"),
        ("Bench", f"{bench.title} ({bench.name})"),
        ("Frappe version", bench.version or "unknown"),
    ]
    if isinstance(plan, AddPlan):
        fields.append(("Source", "Marketplace"))
        for app_, source in plan.picks:
            fields.append(("App", f"{app_.title} ({app_.app}), {source.branch}, "
                                  f"{source.repository}"))  # fmt: skip
    else:
        fields += [
            ("Source", "GitHub"),
            ("App", f"{plan.app.title} ({plan.app.name})"),
            ("Repository", plan.repo.url),
            ("Branch", plan.branch),
            ("App Frappe range", plan.app.frappe_version or "not given"),
        ]
    fields.append(("Action", "FC adds the apps to the bench group"))
    s.out.message("")
    s.out.detail("Add-app preview", fields)
    s.out.message("The apps reach the benches only at the next deploy (bench-deploy).")
    s.out.message("")


def _confirm_bench(s: Session, bench: Bench, confirm: str | None) -> None:
    if s.interactive:
        word = bench.title or bench.name
        typed = picker.ask_text(f"Type the bench title to add the app ({word}):")
        if typed != word:
            raise UsageError("Cancelled. Nothing was sent to FC.", target=f"bench {bench.name}")
        return
    if confirm != bench.name:
        raise UsageError(
            f"The add needs --confirm {bench.name}",
            target=f"bench {bench.name}",
            hint=f"Pass --confirm {bench.name} after you check the preview (--dry-run).",
        )


def add_app_to_bench(
    s: Session,
    bench: Bench,
    opts: AddAppOptions,
    *,
    in_menu: bool = False,
    path: str | None = None,
) -> bool:
    """The work of `bench-add-app` for a known bench. The menu calls it too.

    Returns True when FC accepted the add. Esc at a step raises picker.GoBack in the menu."""
    json_mode = s.out.json_mode
    service = app_service(s)
    name = bench.title or bench.name
    if opts.apps and opts.repo:
        raise UsageError("Use --app or --repo, not both")
    if opts.apps:
        source = MARKET
    elif opts.repo:
        source = GITHUB
    elif not s.interactive:
        raise UsageError("No app given", hint="Give --app <app> or --repo <GitHub URL>.")
    else:
        source = picker.choose(
            "Add an app from",
            [("From the marketplace (search)", MARKET), ("From GitHub", GITHUB)],
            back=in_menu,
            path=path,
        )
    try:
        if source == MARKET:
            plan: AddPlan | GitHubPlan = _market_picks(s, bench, opts, back=in_menu, path=path)
        else:
            plan = _github_plan(s, bench, opts, back=in_menu, path=path)
    except FcmError as err:
        raise _scoped(err, bench.team) from err

    if opts.dry_run:
        if json_mode:
            s.out.emit_json({"dry_run": True, "plan": _add_plan_json(s, plan)})
        else:
            _add_preview(s, plan)
            s.out.message("Dry run: nothing was sent to FC.")
        return False

    if not json_mode:
        _add_preview(s, plan)
    _confirm_bench(s, bench, opts.confirm)

    try:
        if isinstance(plan, AddPlan):
            service.add_market(plan)  # the only write of a marketplace add
            added = [a.app for a, _ in plan.picks]
        else:
            service.add_github(plan)  # the only write of a GitHub add
            added = [plan.app.name]
    except FcmError as err:
        raise _scoped(err, bench.team) from err
    if json_mode:
        s.out.emit_json({"added": True, "plan": _add_plan_json(s, plan)})
    else:
        s.out.message(f"FC added {', '.join(added)} to bench {name}.")
        s.out.message(
            f"They reach the benches at the next deploy. Run: fcm bench-deploy {bench.name}"
        )
    return True


def _parse_sources(values: list[str] | None) -> tuple[tuple[str, str], ...]:
    pairs = []
    for value in values or []:
        app_, sep, source = value.partition("=")
        if not sep or not app_ or not source:
            raise UsageError(f"Bad --source value: {value}", hint="Use --source <app>=<source>.")
        pairs.append((app_, source))
    return tuple(pairs)


@app.command("bench-add-app", rich_help_panel="Bench")
def bench_add_app(
    bench: Annotated[
        str | None,
        typer.Argument(help="Bench name or title. Leave out on a terminal to pick from a list."),
    ] = None,
    team: TeamOpt = None,
    app_names: Annotated[
        list[str] | None,
        typer.Option("--app", help="Marketplace app name to add (repeat for more)."),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="<app>=<FC source>, when an app has more than one."),
    ] = None,
    repo: Annotated[
        str | None, typer.Option("--repo", help="GitHub URL of one app to add.")
    ] = None,
    branch: Annotated[str | None, typer.Option("--branch", help="Branch of --repo.")] = None,
    confirm: Annotated[
        str | None,
        typer.Option("--confirm", help="Bench FC name; required to add without a terminal."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the preview only. Nothing is sent to FC.")
    ] = False,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """Add marketplace or GitHub apps to one bench group. Asks for the bench title."""
    interactive = picker.is_interactive(json_mode)
    if app_names and repo:
        raise UsageError("Use --app or --repo, not both")
    if not interactive:
        if bench is None:
            raise UsageError("No bench given", hint="Give the bench: fcm bench-add-app <bench>")
        if not app_names and not repo:
            raise UsageError("No app given", hint="Give --app <app> or --repo <GitHub URL>.")
    options = AddAppOptions(
        apps=tuple(app_names or ()),
        sources=_parse_sources(source),
        repo=repo,
        branch=branch,
        confirm=confirm,
        dry_run=dry_run,
    )
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        target = _pick_bench(s, teams, bench)
        if not interactive and not dry_run and confirm != target.name:
            _confirm_bench(s, target, confirm)  # raises before any write
        add_app_to_bench(s, target, options)


# --- site-install-app -----------------------------------------------------------------


def _site_app_label(a: SiteApp) -> str:
    return f"{a.title} ({a.app}, {a.branch or 'unknown branch'})"


def _install_plan_json(s: Session, plan: InstallPlan) -> dict:
    site = plan.site
    return {
        "profile": s.profile.label,
        "team": _team_json(site.team),
        "bench": {"name": site.bench, "title": site.bench_title},
        "site": site.name,
        "site_status": plan.status,
        "app": {"name": plan.app.app, "title": plan.app.title, "branch": plan.app.branch},
    }


def _install_preview(s: Session, plan: InstallPlan) -> None:
    site = plan.site
    s.out.message("")
    s.out.detail(
        "Install preview",
        [
            ("Profile", s.profile.label),
            ("Team", team_label(site.team)),
            ("Owner", site.team.owner or "unknown"),
            ("Bench", f"{site.bench_title} ({site.bench})"),
            ("Site", site.name),
            ("Site status", plan.status),
            ("App", _site_app_label(plan.app)),
            ("Action", "FC installs the app on the live site"),
        ],
    )
    s.out.message("")


def _confirm_site(s: Session, site: Site, confirm: str | None) -> None:
    if s.interactive:
        typed = picker.ask_text(f"Type the site name to install the app ({site.name}):")
        if typed != site.name:
            raise UsageError("Cancelled. Nothing was sent to FC.", target=f"site {site.name}")
        return
    if confirm != site.name:
        raise UsageError(
            f"The install needs --confirm {site.name}",
            target=f"site {site.name}",
            hint=f"Pass --confirm {site.name} after you check the preview (--dry-run).",
        )


def _install_stage(state: MigrateState) -> str:
    return INSTALL_STAGE_TEXT[state.stage]


def install_view(title: str, clock=time.monotonic) -> WatchView:
    """The live install screen (see cli/watch.py)."""
    return WatchView(
        "Install",
        title,
        stage_text=_install_stage,
        table=lambda state, running=None: steps_table(state.steps, running),
        clock=clock,
    )


def _watch_install(s: Session, service: AppService, plan: InstallPlan) -> MigrateState:
    final: MigrateState | None = None
    states = service.watch_install(plan, sleep=time.sleep)
    if s.out.json_mode:
        for state in changes(states):
            s.out.emit_json_line({"event": "progress", **_state_json(state)})
            final = state
    elif s.interactive:
        view = install_view(plan.site.name)
        with Live(view, console=s.out.console, refresh_per_second=4, transient=False) as live:
            try:
                for state in states:
                    view.update(state)
                    final = state
            finally:
                view.done = True
                live.refresh()
    else:
        for state in changes(states):
            now = f" - {state.current_step.label}" if state.current_step else ""
            s.out.message(f"{INSTALL_STAGE_TEXT[state.stage]}{now}")
            final = state
    assert final is not None
    return final


def install_app_on_site(
    s: Session,
    site: Site,
    opts: InstallAppOptions,
    *,
    in_menu: bool = False,
    path: str | None = None,
) -> None:
    """The work of `site-install-app` for a known site. The menu calls it too.

    Ctrl+C in the watch: exit 130, or WatchStopped in the menu."""
    json_mode = s.out.json_mode
    service = app_service(s)
    try:
        check = service.check_site(site)
        apps = service.offered_site_apps(site)
    except FcmError as err:
        raise _scoped(err, site.team) from err

    if opts.app:
        chosen = service.pick_site_app(site, apps, opts.app)
    else:
        if not apps or not any(a.pickable for a in apps):
            if json_mode:
                s.out.emit_json({"site": site.name, "installed": False, "apps": []})
            if apps:
                s.out.message(
                    f"Every app that site {site.name} can get has marketplace plans. "
                    "Install it from the FC dashboard."
                )
            else:
                s.out.message(f"Site {site.name} already has every app of its bench.")
            return
        if not s.interactive:
            raise UsageError("No app given", hint="Give the app: --app <app>")
        chosen = picker.choose(
            f"App to install on {site.name}",
            [(_site_app_label(a), a) for a in apps],
            back=in_menu,
            path=path,
            disabled=lambda a: None if a.pickable else PLANS_NOTE,
        )
    plan = InstallPlan(site=site, status=check.status, app=chosen)

    if opts.dry_run:
        if json_mode:
            s.out.emit_json({"dry_run": True, "plan": _install_plan_json(s, plan)})
        else:
            _install_preview(s, plan)
            s.out.message("Dry run: nothing was sent to FC.")
        return

    if not json_mode:
        _install_preview(s, plan)
    _confirm_site(s, site, opts.confirm)

    try:
        service.install(plan)  # the only write
    except FcmError as err:
        raise _scoped(err, site.team) from err
    if json_mode:
        s.out.emit_json_line({"event": "accepted", "plan": _install_plan_json(s, plan)})
    else:
        s.out.message(f"FC accepted the install of {chosen.app} on {site.name}.")
    if opts.no_wait:
        s.out.message(f"The install started. Follow it with: fcm site-show {site.name}")
        return

    try:
        final = _watch_install(s, service, plan)
    except KeyboardInterrupt:
        s.out.message("")
        s.out.message(
            f"Stopped watching. The install continues on FC. Run: fcm site-show {site.name}"
        )
        if in_menu:
            raise WatchStopped from None
        raise typer.Exit(130) from None
    except FcmError as err:
        raise _scoped(err, site.team) from err

    if json_mode:
        s.out.emit_json_line({"event": "result", **_state_json(final)})
    else:
        s.out.message("")
        s.out.detail(
            f"Install finished: {chosen.app} is installed on the site",
            [
                ("Site", site.name),
                ("App", chosen.app),
                ("Job", final.job),
                ("Site status", final.site_status or "unknown"),
            ],
        )


@app.command("site-install-app", rich_help_panel="Site")
def site_install_app(
    site: Annotated[
        str | None,
        typer.Argument(help="Site name. Leave out on a terminal to pick team, bench, site."),
    ] = None,
    team: TeamOpt = None,
    app_name: Annotated[
        str | None,
        typer.Option("--app", help="App name to install. Leave out to pick on a terminal."),
    ] = None,
    confirm: Annotated[
        str | None,
        typer.Option("--confirm", help="Site name; required to install without a terminal."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Run the checks and show the preview only.")
    ] = False,
    no_wait: Annotated[
        bool, typer.Option("--no-wait", help="Return when FC accepts the install.")
    ] = False,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """Install an app of the bench on one site. Shows a preview and asks for the site name."""
    interactive = picker.is_interactive(json_mode)
    if not interactive:
        if site is None:
            raise UsageError("No site given", hint="Give the site: fcm site-install-app <site>")
        if app_name is None:
            raise UsageError("No app given", hint="Give the app: --app <app>")
    options = InstallAppOptions(app=app_name, confirm=confirm, dry_run=dry_run, no_wait=no_wait)
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        target = resolve_site(s, teams, site) if site else walk_to_site(s, teams)
        if not interactive and not dry_run and confirm != target.name:
            _confirm_site(s, target, confirm)  # raises before any check or write
        install_app_on_site(s, target, options)
