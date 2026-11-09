"""`fcm bench-show` and `fcm bench-deploy`.

`bench-deploy` is the only command that changes FC. It walks: bench, app updates, sites
(none selected by default), preview, typed confirmation, deploy, progress, result.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Annotated

import typer
from rich.console import Group
from rich.live import Live
from rich.markup import escape
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from fc_manager.cli import picker
from fc_manager.cli.common import (
    DebugOpt,
    JsonOpt,
    ProfileOpt,
    Session,
    TeamOpt,
    count,
    explain_team_error,
    raise_failures,
    scope_teams,
    session,
    team_label,
)
from fc_manager.cli.inventory import _bench_json, _resolve_bench
from fc_manager.cli.root import app
from fc_manager.deploy import (
    AppUpdate,
    DeployInfo,
    DeployPlan,
    DeployService,
    DeployState,
)
from fc_manager.errors import DeployFailed, FcmError, NotFound, UsageError
from fc_manager.inventory import Bench
from fc_manager.output import Column

STAGE_TEXT = {
    "idle": "no deploy running",
    "starting": "waiting for FC to start the deploy",
    "validating": "FC is checking the deploy",
    "building": "building the new bench image",
    "finishing": "build done; FC is creating the new bench",
    "updating_sites": "bench ready; FC is updating the selected sites (backup, move, migrate)",
    "success": "finished",
    "failure": "failed",
}


# --- shared ---------------------------------------------------------------------------


def _scoped(err: FcmError, bench: Bench) -> FcmError:
    """Name the team (and its owner for a permission error), unless a bench is the target."""
    if err.target and not err.target.startswith("team "):
        return err
    return explain_team_error(err, bench.team)


def _team_option(team) -> str:
    label = team_label(team)
    return f"{label}  - {team.owner}" if team.owner and team.owner not in label else label


def _pick_bench(s: Session, teams, query: str | None, *, start_team=None) -> Bench:
    """The bench from its name or title, or, when it is missing, from a walk.

    On a terminal the walk is: team (skipped when only one team is in scope), then a bench
    of that team. Only that team is queried. Esc on the bench step goes back to the team
    step. `start_team` opens the walk at the bench step of that team."""
    if query:
        bench = _resolve_bench(s, teams, query)
        assert bench is not None
        return bench
    if not s.interactive:
        raise UsageError("No bench given", hint="Give the bench by name or title.")
    many = len(teams) > 1
    team = start_team
    while True:
        if team is None:
            team = (
                picker.choose("Team", [(_team_option(t), t) for t in teams]) if many else teams[0]
            )
        result = s.inventory.benches([team])
        if result.failures:
            raise_failures(result, [team])
        if not result.rows:
            if not many:
                raise NotFound(f"No benches found in team {team.display}")
            s.out.message(f"No benches in team {team.display}. Pick another team.")
            team = None
            continue
        options = [(f"{b.title} ({b.name})", b) for b in result.rows]
        try:
            return picker.choose(f"Bench in {team.display}", options, back=many)
        except picker.GoBack:
            team = None


def _app_note(app: AppUpdate) -> str:
    notes = []
    if app.will_branch_change:
        notes.append(f"branch {app.current_branch} -> {app.branch}")
    if app.next and app.next.message:
        notes.append(app.next.message[:60])
    return "; ".join(notes)


def _app_label(app: AppUpdate) -> str:
    note = _app_note(app)
    return f"{app.app}  {app.current_version} -> {app.next_version}" + (
        f"  ({note})" if note else ""
    )


def _app_json(app: AppUpdate) -> dict:
    return {
        "app": app.app,
        "title": app.title,
        "branch": app.branch,
        "current": app.current_version,
        "next": app.next_version if app.has_update else None,
        "update_available": app.has_update,
        "will_branch_change": app.will_branch_change,
    }


def _state_json(state: DeployState) -> dict:
    return {
        "stage": state.stage,
        "build": state.build or None,
        "status": state.status or None,
        "steps": [asdict(step) for step in state.steps],
        "message": state.message or None,
        "sites": [{"site": name, "moved": moved} for name, moved in state.sites],
    }


def _duration(value: str) -> str:
    """FC gives build step durations as bare seconds ("15.8"). Add the unit."""
    try:
        float(value)
    except ValueError:
        return value
    return f"{value} s"


def _sites_line(state: DeployState) -> str:
    return ", ".join(f"{name} ({'moved' if moved else 'waiting'})" for name, moved in state.sites)


def _steps_table(state: DeployState, running: dict[str, str] | None = None) -> Table:
    """`running` maps a step label to the time text to show for a running step."""
    table = Table(show_edge=False, pad_edge=False, header_style="bold")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Time")
    for step in state.steps:
        status = step.status + (" (cached)" if step.cached and step.status == "Success" else "")
        time_text = (running or {}).get(step.label, _duration(step.duration))
        table.add_row(escape(step.label), escape(status), escape(time_text))
    return table


# --- bench-show -----------------------------------------------------------------------


@app.command("bench-show", rich_help_panel="Bench")
def bench_show(
    bench: Annotated[
        str | None,
        typer.Argument(help="Bench name or title. Leave out on a terminal to pick from a list."),
    ] = None,
    team: TeamOpt = None,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """Show one bench: apps with updates, sites, and a running deploy."""
    if bench is None and not picker.is_interactive(json_mode):
        raise UsageError("No bench given", hint="Give the bench: fcm bench-show <bench>")
    with session(profile, json_mode, debug) as s:
        show_bench(s, _pick_bench(s, scope_teams(s, team), bench))


def show_bench(s: Session, target: Bench) -> None:
    """The work of `bench-show` for a known bench. The menu calls it too."""
    json_mode = s.out.json_mode
    service = DeployService(s.client)
    try:
        info = service.info(target)
        state = service.state(target) if info.busy else DeployState(stage="idle")
    except FcmError as err:
        raise _scoped(err, target) from err

    if json_mode:
        s.out.emit_json(
            {
                "bench": _bench_json(target),
                "update_available": bool(info.updates or info.removed_apps),
                "apps": [_app_json(a) for a in info.apps],
                "removed_apps": info.removed_apps,
                "sites": [{"name": x.name, "server": x.server} for x in info.sites],
                "last_build": info.last_build or None,
                "deploy": _state_json(state),
            }
        )
        return
    deploy_text = STAGE_TEXT[state.stage]
    if state.current_step:
        deploy_text += f" (now: {state.current_step.label})"
    s.out.detail(
        f"Bench {target.title or target.name}",
        [
            ("Team", team_label(target.team)),
            ("Bench", f"{target.title} ({target.name})"),
            ("Version", target.version),
            ("Status", target.status),
            ("Updates", count(len(info.updates), "app") if info.updates else "none"),
            ("Deploy", deploy_text),
        ],
    )
    s.out.message("")
    s.out.table(
        [
            Column("App", lambda a: a.app),
            Column("Current", lambda a: a.current_version),
            Column("Update", lambda a: a.next_version if a.has_update else ""),
            Column("Branch", lambda a: a.branch),
            Column("Note", lambda a: _app_note(a) if a.has_update else ""),
        ],
        info.apps,
        json_rows=[],
        summary=f"{count(len(info.apps), 'app')}, {count(len(info.updates), 'update')}",
        empty="FC reports no apps for this bench.",
    )
    if info.removed_apps:
        s.out.message(f"Removed apps (go away at the next deploy): {', '.join(info.removed_apps)}")
    s.out.message("")
    s.out.table(
        [Column("Site", lambda x: x.name), Column("Server", lambda x: x.server)],
        info.sites,
        json_rows=[],
        summary=f"{count(len(info.sites), 'site')} on this bench",
        empty="No active site on this bench.",
    )
    if state.steps:
        s.out.message("")
        s.out.console.print(_steps_table(state))


# --- bench-deploy ---------------------------------------------------------------------


def _choose_apps(s: Session, info: DeployInfo, *, back: bool, path: str | None = None) -> list[str]:
    if not info.updates:
        return []
    while True:
        chosen = picker.choose_many(
            "App updates to deploy",
            [(_app_label(a), a.app) for a in info.updates],
            selected=True,
            back=back,
            path=path,
        )
        if chosen or info.removed_apps:
            return chosen
        s.out.message("Select at least one app to deploy.")


def _choose_sites(s: Session, info: DeployInfo, *, path: str | None = None) -> list[str]:
    if not info.sites:
        s.out.message("No active site on this bench: the deploy is bench only.")
        return []
    return picker.choose_many(
        "Sites to update after the build (none = bench only)",
        [(x.name, x.name) for x in info.sites],
        selected=False,
        back=True,
        path=path,
    )


def _preview(s: Session, plan: DeployPlan) -> None:
    bench = plan.bench
    sites = (
        "Bench only: no site is updated"
        if plan.bench_only
        else ", ".join(x.name for x in plan.sites) + " (a backup is taken before each update)"
    )
    s.out.message("")
    s.out.detail(
        "Deploy preview",
        [
            ("Profile", s.profile.label),
            ("Team", team_label(bench.team)),
            ("Owner", bench.team.owner or "unknown"),
            ("Bench", f"{bench.title} ({bench.name})"),
            ("Apps", count(len(plan.apps), "app")),
            ("Removed apps", ", ".join(plan.removed_apps) or "none"),
            ("Sites", sites),
        ],
    )
    if plan.apps:
        s.out.message("")
        s.out.table(
            [
                Column("App", lambda a: a.app),
                Column("From", lambda a: a.current_version),
                Column("To", lambda a: a.next_version),
                Column("Note", _app_note),
            ],
            plan.apps,
            json_rows=[],
            summary=count(len(plan.apps), "app update"),
            empty="",
        )
    s.out.message("")


def _plan_json(s: Session, plan: DeployPlan) -> dict:
    return {
        "profile": s.profile.label,
        "team": {
            "name": plan.bench.team.name,
            "label": plan.bench.team.display,
            "owner": plan.bench.team.owner,
        },
        "bench": {"name": plan.bench.name, "title": plan.bench.title},
        "apps": [_app_json(a) for a in plan.apps],
        "removed_apps": plan.removed_apps,
        "sites": [x.name for x in plan.sites],
        "bench_only": plan.bench_only,
    }


def _confirm(s: Session, plan: DeployPlan, confirm: str | None) -> None:
    bench = plan.bench
    if s.interactive:
        word = bench.title or bench.name
        typed = picker.ask_text(f"Type the bench title to deploy ({word}):")
        if typed != word:
            raise UsageError("Cancelled. Nothing was sent to FC.", target=f"bench {bench.name}")
        return
    if confirm != bench.name:
        raise UsageError(
            f"The deploy needs --confirm {bench.name}",
            target=f"bench {bench.name}",
            hint=f"Pass --confirm {bench.name} after you check the preview (--dry-run).",
        )


STALE_SECONDS = 10.0  # no FC answer for this long: the status line turns yellow


def _seconds(value: float) -> str:
    value = int(value)
    return f"{value // 60}m{value % 60:02d}s" if value >= 60 else f"{value} s"


class _WatchView:
    """The live deploy screen. The status line is built again at each screen refresh, so
    "last FC answer N s ago" grows when a poll hangs, even while no new state arrives."""

    def __init__(self, title: str, clock=time.monotonic):
        self.title = title
        self.clock = clock
        self.started = clock()
        self.state: DeployState | None = None
        self.running_since: dict[str, float] = {}  # step label -> first poll that saw Running
        self.spinner = Spinner("dots")
        self.done = False

    def update(self, state: DeployState) -> None:
        self.state = state
        for step in state.steps:
            if step.status == "Running":
                self.running_since.setdefault(step.label, state.checked_at or self.clock())

    def status_line(self) -> Text:
        now = self.clock()
        state = self.state
        stage = STAGE_TEXT[state.stage] if state else "sending the first poll to FC"
        step = state.current_step if state and not state.final else None
        line = Text.assemble(
            ("Deploy ", "bold"),
            (self.title, "bold"),
            f": {stage}",
            f" - {step.label}" if step else "",
        )
        line.append(f"\n  elapsed {_seconds(now - self.started)}")
        if self.done:
            return line
        last = state.checked_at if state else self.started
        age = now - last
        if age >= STALE_SECONDS:
            line.append(f"  |  no answer from FC for {_seconds(age)}", style="yellow")
        else:
            polls = state.polls if state else 0
            line.append(f"  |  last FC answer {_seconds(age)} ago (poll {polls})")
        return line

    def __rich__(self):
        running = {}
        if self.state and not self.done:
            now = self.clock()
            running = {
                step.label: f"running {_seconds(now - self.running_since[step.label])}"
                for step in self.state.steps
                if step.status == "Running" and step.label in self.running_since
            }
        parts = [_steps_table(self.state, running)] if self.state else []
        if self.state and self.state.stage == "updating_sites":
            parts.append(Text(f"Sites: {_sites_line(self.state)}"))
        if self.done:
            return Group(self.status_line(), *parts)
        self.spinner.update(text=self.status_line())
        return Group(self.spinner, *parts)


def _changes(states):
    """Only the states with new FC data (the watch yields one per poll)."""
    last = None
    for state in states:
        if state != last:
            last = state
            yield state


def _watch(s: Session, service: DeployService, plan: DeployPlan) -> DeployState:
    bench = plan.bench
    final: DeployState | None = None
    states = service.watch(plan, sleep=time.sleep)
    if s.out.json_mode:
        for state in _changes(states):
            s.out.emit_json_line({"event": "progress", **_state_json(state)})
            final = state
    elif s.interactive:
        view = _WatchView(bench.title or bench.name)
        with Live(view, console=s.out.console, refresh_per_second=4, transient=False) as live:
            try:
                for state in states:
                    view.update(state)
                    final = state
            finally:
                view.done = True
                live.refresh()
    else:
        for state in _changes(states):
            now = f" - {state.current_step.label}" if state.current_step else ""
            if state.stage == "updating_sites":
                now = f" - {_sites_line(state)}"
            s.out.message(f"{STAGE_TEXT[state.stage]}{now}")
            final = state
    assert final is not None
    return final


@app.command("bench-deploy", rich_help_panel="Bench")
def bench_deploy(
    bench: Annotated[
        str | None,
        typer.Argument(help="Bench name or title. Leave out on a terminal to pick from a list."),
    ] = None,
    team: TeamOpt = None,
    app: Annotated[
        list[str] | None, typer.Option("--app", help="App to deploy (repeat for more).")
    ] = None,
    all_apps: Annotated[
        bool, typer.Option("--all-apps", help="Deploy every app with an update.")
    ] = False,
    site: Annotated[
        list[str] | None,
        typer.Option("--site", help="Site to update after the build (repeat). None = bench only."),
    ] = None,
    confirm: Annotated[
        str | None,
        typer.Option("--confirm", help="Bench FC name; required to deploy without a terminal."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the preview only. Nothing is sent to FC.")
    ] = False,
    no_wait: Annotated[
        bool, typer.Option("--no-wait", help="Return when FC accepts the deploy.")
    ] = False,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """Deploy app updates to one bench. Shows a preview and asks for the bench title."""
    interactive = picker.is_interactive(json_mode)
    if app and all_apps:
        raise UsageError("Use --app or --all-apps, not both")
    if not interactive:
        if bench is None:
            raise UsageError("No bench given", hint="Give the bench: fcm bench-deploy <bench>")
        if not app and not all_apps:
            raise UsageError(
                "No app selected", hint="Use --app <app> (repeat for more) or --all-apps."
            )

    options = DeployOptions(
        apps=list(app) if app else None,
        all_apps=all_apps,
        sites=list(site) if site else None,
        confirm=confirm,
        dry_run=dry_run,
        no_wait=no_wait,
    )
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        target = _pick_bench(s, teams, bench)
        if not interactive and not dry_run and confirm != target.name:
            _confirm(s, DeployPlan(target, [], [], [], ""), confirm)  # raises: no write yet
        repick = None
        if bench is None:  # Esc on the app step goes back to the bench step of the walk

            def repick(current: Bench) -> Bench:
                return _pick_bench(s, teams, None, start_team=current.team)

        deploy_bench(s, target, options, repick=repick)


@dataclass(frozen=True)
class DeployOptions:
    apps: list[str] | None = None  # None: not given (pick on a terminal)
    all_apps: bool = False
    sites: list[str] | None = None  # None: not given (pick on a terminal; bench only in a script)
    confirm: str | None = None
    dry_run: bool = False
    no_wait: bool = False


class WatchStopped(Exception):  # noqa: N818 - a signal, not an error
    """Ctrl+C stopped the watch in the menu. The deploy continues on FC."""


def deploy_bench(
    s: Session,
    target: Bench,
    opts: DeployOptions,
    *,
    repick: Callable[[Bench], Bench] | None = None,
    in_menu: bool = False,
    path: str | None = None,
) -> None:
    """The work of `bench-deploy` for a known bench. The menu calls it too.

    Esc on the app step: with `repick`, pick another bench; in the menu, raise
    picker.GoBack to the menu. Ctrl+C in the watch: exit 130, or WatchStopped in the menu."""
    json_mode = s.out.json_mode
    interactive = s.interactive
    app, all_apps, site, confirm = opts.apps, opts.all_apps, opts.sites, opts.confirm
    service = DeployService(s.client)
    back = repick is not None or in_menu
    while True:  # the walk; Esc on the app step goes back to the bench step
        try:
            info = service.info(target)
        except FcmError as err:
            raise _scoped(err, target) from err
        if info.busy:
            raise UsageError(
                f"A deploy is already running on bench {target.title or target.name}",
                target=f"bench {target.name}",
                hint=f"Run: fcm bench-show {target.name}",
            )
        if info.nothing_to_deploy:
            if json_mode:
                s.out.emit_json({"bench": target.name, "status": "up_to_date"})
            else:
                s.out.message(
                    f"Bench {target.title or target.name} is up to date. Nothing to deploy."
                )
            return
        if not interactive:
            plan = service.plan(info, None if all_apps else app, site or [])
            break
        try:
            apps = (
                None
                if all_apps
                else list(app)
                if app
                else _choose_apps(s, info, back=back, path=path)
            )
        except picker.GoBack:
            if repick is None:
                raise
            target = repick(target)
            continue
        try:
            sites = list(site) if site else _choose_sites(s, info, path=path)
        except picker.GoBack:
            continue  # back to the app step: info is read again, still one bench
        plan = service.plan(info, apps, sites)
        break

    if opts.dry_run:
        if json_mode:
            s.out.emit_json({"dry_run": True, "plan": _plan_json(s, plan)})
        else:
            _preview(s, plan)
            s.out.message("Dry run: nothing was sent to FC.")
        return

    if not json_mode:
        _preview(s, plan)
    _confirm(s, plan, confirm)

    try:
        ref = service.start(plan)  # the only write
    except FcmError as err:
        raise _scoped(err, target) from err
    if json_mode:
        s.out.emit_json_line({"event": "accepted", "ref": ref, "plan": _plan_json(s, plan)})
    else:
        s.out.message(f"FC accepted the deploy ({ref}).")
    if opts.no_wait:
        s.out.message(f"Follow it with: fcm bench-show {target.name}")
        return

    try:
        final = _watch(s, service, plan)
    except KeyboardInterrupt:
        s.out.message("")
        s.out.message(
            f"Stopped watching. The deploy continues on FC. Run: fcm bench-show {target.name}"
        )
        if in_menu:
            raise WatchStopped from None
        raise typer.Exit(130) from None
    except DeployFailed as err:
        raise _scoped(err, target) from err
    except FcmError as err:
        raise _scoped(err, target) from err

    if json_mode:
        s.out.emit_json_line({"event": "result", **_state_json(final)})
    else:
        s.out.message("")
        s.out.detail(
            "Deploy finished",
            [
                ("Bench", f"{target.title} ({target.name})"),
                ("Apps", ", ".join(f"{a.app} {a.next_version}" for a in plan.apps) or "none"),
                (
                    "Sites",
                    "Bench only: no site is updated"
                    if plan.bench_only
                    else ", ".join(f"{n} (updated)" for n, _ in final.sites),
                ),
            ],
        )
