"""`fcm` with no command: the menu walk (team, then bench, then an action for that bench).

The menu only routes. Each action runs the same work function as its direct command
(`show_bench`, `deploy_bench`, `migrate_site`, `update_site`), so the FC requests, the
preview and the typed confirmation are the same code. Every prompt shows the target path:
profile > team > bench, and > site after the site step of a site action.

A new action is one `Action` entry in `ACTIONS`. A site action gets the site step (a site
of the picked bench) before it runs. Its `site_filter` can narrow that list, with
`site_empty` as the message when no site is left.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version as package_version
from typing import Annotated

import typer

from fc_manager import config, credentials
from fc_manager.cli import deploy, migrate, picker, update
from fc_manager.cli import profile as profile_cli
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
from fc_manager.errors import FcmError, NotFound, UsageError
from fc_manager.inventory import Bench, Site, Team
from fc_manager.output import Output

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
    site_filter: Callable[[Site], bool] | None = None
    site_empty: str | None = None  # "{bench}" is the bench title

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
    Action("update", "Update a site", "site-update", "site",
           lambda s, bench, site, path: update.update_site(
               s, site, update.UpdateOptions(), in_menu=True, path=path),
           site_filter=update.has_update, site_empty=update.EMPTY_SITE_STEP),
]  # fmt: skip


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"fcm {package_version('fc-manager')}")
        raise typer.Exit(0)


VersionOpt = Annotated[
    bool,
    typer.Option(
        "--version", callback=_show_version, is_eager=True, help="Show the version and exit."
    ),
]

SETUP_PROFILE = "default"
WELCOME = (
    "Welcome to fcm. No profile is set up yet.\n"
    "A profile holds one FC API key and secret. To make one, open the FC dashboard:\n"
    "Settings > Profile & Team > API Access. The secret goes into the OS keyring only."
)


def needs_setup(profile_option: str | None) -> bool:
    """True when nothing can give credentials: no profile picked or saved, no env vars."""
    if profile_option or os.environ.get(credentials.ENV_PROFILE):
        return False
    if config.load().profiles:
        return False
    return credentials.env_credentials() is None


def first_run() -> str:
    """The first-run setup: add the first profile, as profile-add does. Returns its name."""
    out = Output(json_mode=False)
    if not credentials.keyring_usable():
        raise UsageError(
            "No profile is set up, and no secure OS keyring is available on this host",
            hint=credentials.ENV_HINT,
        )
    out.message(WELCOME)
    name = typer.prompt("Profile name", default=SETUP_PROFILE).strip()
    try:
        account = profile_cli.add_profile(out, name)
    except FcmError as err:  # nothing was saved: the retry is the setup itself
        err.hint = "Nothing was saved. Run fcm again to retry the setup."
        raise
    out.message(f"Profile {name} saved: user {account.user}. Opening the menu.")
    return name


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context, profile: ProfileOpt = None, version: VersionOpt = False) -> None:
    """Explore Frappe Cloud teams, benches and sites, and deploy app updates to a bench.

    Run `fcm` with no command on a terminal to open the menu: team, bench, then an action."""
    if ctx.invoked_subcommand is not None:
        return
    if not picker.is_interactive(json_mode=False):
        typer.echo(ctx.get_help())
        raise typer.Exit(0)
    try:
        if needs_setup(profile):
            profile = first_run()
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
                site = choose_site(
                    s,
                    bench,
                    back=True,
                    path=path,
                    only=action.site_filter,
                    empty=action.site_empty,
                )
                if site is None:  # no site is left; choose_site said so
                    continue
            action.run(s, bench, site, target_path(s, team, bench, site))
        except picker.GoBack:
            pass  # Esc at the site step, or at the app step of the deploy
        except deploy.WatchStopped:
            pass  # the action already said that the job continues on FC
        except FcmError as err:
            s.out.error(err)  # also a cancelled confirmation: nothing was sent
        s.out.message("")
