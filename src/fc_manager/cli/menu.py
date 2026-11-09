"""`fcm` with no command: the menu walk (team, then bench, then an action for that bench).

The menu only routes. Each action runs the same work function as its direct command
(`show_bench`, `deploy_bench`, `migrate_site`), so the FC requests, the preview and the
typed confirmation are the same code. Every prompt shows the target path:
profile > team > bench, and > site after the site step of a site action.

A new action is one `Action` entry in `ACTIONS`. A site action gets the site step (a site
of the picked bench) before it runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import typer

from fc_manager.cli import deploy, migrate, picker
from fc_manager.cli.common import (
    ProfileOpt,
    Session,
    raise_failures,
    scope_teams,
    session,
    target_path,
)
from fc_manager.cli.inventory import choose_site
from fc_manager.cli.root import app
from fc_manager.errors import FcmError, NotFound
from fc_manager.inventory import Bench, Site, Team

OTHER_BENCH, QUIT = "bench", "quit"


@dataclass(frozen=True)
class Action:
    """One menu entry. `run(s, bench, site, path)` gets the picked site for scope "site",
    or None for scope "bench"."""

    name: str
    label: str
    command: str
    scope: str  # "bench" or "site"
    run: Callable[[Session, Bench, Site | None, str], None]

    @property
    def title(self) -> str:
        return f"{self.label} ({self.command})"


ACTIONS = [
    Action("show", "Show bench", "bench-show", "bench",
           lambda s, bench, site, path: deploy.show_bench(s, bench)),
    Action("deploy", "Deploy app updates", "bench-deploy", "bench",
           lambda s, bench, site, path: deploy.deploy_bench(
               s, bench, deploy.DeployOptions(), in_menu=True, path=path)),
    Action("migrate", "Migrate a site", "site-migrate", "site",
           lambda s, bench, site, path: migrate.migrate_site(
               s, site, migrate.MigrateOptions(), in_menu=True, path=path)),
]  # fmt: skip


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
                        path=target_path(s),
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
    return picker.choose("Bench", options, back=back, path=target_path(s, team))


def _action_loop(s: Session, team: Team, bench: Bench) -> str:
    """Run actions on one bench until the user goes back (OTHER_BENCH) or quits (QUIT)."""
    path = target_path(s, team, bench)
    entries = [(a.title, a) for a in ACTIONS]
    entries += [("Pick another bench", OTHER_BENCH), ("Quit", QUIT)]
    while True:
        try:
            action = picker.choose("Action", entries, back=True, path=path)
        except picker.GoBack:
            return OTHER_BENCH
        if not isinstance(action, Action):
            return action
        try:
            site = None
            if action.scope == "site":
                site = choose_site(s, bench, back=True, path=path)
                if site is None:  # the bench has no site; choose_site said so
                    continue
            action.run(s, bench, site, target_path(s, team, bench, site))
        except picker.GoBack:
            pass  # Esc at the site step, or at the app step of the deploy
        except deploy.WatchStopped:
            pass  # the action already said that the job continues on FC
        except FcmError as err:
            s.out.error(err)  # also a cancelled confirmation: nothing was sent
        s.out.message("")
