"""`fcm` with no command: the menu walk (team, then bench, then an action for that bench).

The menu only routes. Each action runs the same work function as its direct command
(`show_bench`, `deploy_bench`), so the FC requests, the preview and the typed confirmation
are the same code. Every prompt shows the target path: profile > team > bench.
"""

from __future__ import annotations

import typer

from fc_manager.cli import deploy, picker
from fc_manager.cli.common import ProfileOpt, Session, raise_failures, scope_teams, session
from fc_manager.cli.root import app
from fc_manager.errors import FcmError, NotFound
from fc_manager.inventory import Bench, Team

SHOW, DEPLOY, OTHER_BENCH, QUIT = "show", "deploy", "bench", "quit"
ACTIONS = [
    ("Show bench (bench-show)", SHOW),
    ("Deploy app updates (bench-deploy)", DEPLOY),
    ("Pick another bench", OTHER_BENCH),
    ("Quit", QUIT),
]


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context, profile: ProfileOpt = None) -> None:
    """Explore Frappe Cloud teams, benches and sites, and deploy app updates to a bench.

    Run `fcm` with no command on a terminal to open the menu: team, bench, then an action."""
    if ctx.invoked_subcommand is not None:
        return
    if not picker.is_interactive(json_mode=False):
        typer.echo(ctx.get_help())
        raise typer.Exit(0)
    try:
        run(profile)
    except picker.Cancelled:  # Ctrl+C at a menu prompt
        typer.echo("Cancelled, nothing done.")
        raise typer.Exit(130) from None


def _path(s: Session, team: Team | None = None, bench: Bench | None = None) -> str:
    parts = [s.profile.label]
    if team is not None:
        parts.append(team.display)
    if bench is not None:
        parts.append(f"{bench.title or bench.name} ({bench.name})")
    return " > ".join(parts)


def run(profile: str | None) -> None:
    """The menu loop. Returns when the user quits or presses Esc at the team step."""
    with session(profile, False, False) as s:
        teams = scope_teams(s, None)
        many = len(teams) > 1
        team: Team | None = None if many else teams[0]
        while True:
            if team is None:
                try:
                    team = picker.choose(
                        "Team",
                        [(deploy._team_option(t), t) for t in teams],
                        back=True,
                        path=_path(s),
                    )
                except picker.GoBack:
                    return
            try:
                bench = _bench_step(s, team, back=True)
            except picker.GoBack:
                if not many:
                    return
                team = None
                continue
            if bench is None:  # no bench in this team
                team = None
                continue
            if _action_loop(s, team, bench) == QUIT:
                return


def _bench_step(s: Session, team: Team, *, back: bool) -> Bench | None:
    result = s.inventory.benches([team])  # this team only
    if result.failures:
        raise_failures(result, [team])
    if not result.rows:
        if len(s.inventory.teams()) <= 1:
            raise NotFound(f"No benches found in team {team.display}")
        s.out.message(f"No benches in team {team.display}. Pick another team.")
        return None
    options = [(f"{b.title} ({b.name})", b) for b in result.rows]
    return picker.choose("Bench", options, back=back, path=_path(s, team))


def _action_loop(s: Session, team: Team, bench: Bench) -> str:
    """Run actions on one bench until the user goes back (OTHER_BENCH) or quits (QUIT)."""
    path = _path(s, team, bench)
    while True:
        try:
            action = picker.choose("Action", ACTIONS, back=True, path=path)
        except picker.GoBack:
            return OTHER_BENCH
        if action in (OTHER_BENCH, QUIT):
            return action
        try:
            if action == SHOW:
                deploy.show_bench(s, bench)
            else:
                deploy.deploy_bench(s, bench, deploy.DeployOptions(), in_menu=True, path=path)
        except picker.GoBack:
            pass  # Esc at the app step of the deploy: back to this menu
        except deploy.WatchStopped:
            pass  # deploy_bench already said that the deploy continues on FC
        except FcmError as err:
            s.out.error(err)  # also a cancelled confirmation: nothing was sent
        s.out.message("")
