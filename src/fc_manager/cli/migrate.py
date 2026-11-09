"""`fcm site-migrate`: run `bench migrate` on one FC site.

The walk is: site (or team, bench, site on a terminal), checks, preview, typed site
name, migrate request, job watch, result. The only write is the migrate request.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Annotated

import typer
from rich.live import Live
from rich.table import Table

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
from fc_manager.cli.deploy import WatchStopped
from fc_manager.cli.inventory import resolve_site, walk_to_site
from fc_manager.cli.root import app
from fc_manager.cli.watch import WatchView, changes, steps_table
from fc_manager.errors import FcmError, UsageError
from fc_manager.inventory import Site
from fc_manager.migrate import MigratePlan, MigrateService, MigrateState

STAGE_TEXT = {
    "finding": "FC accepted the migrate; waiting for its job to show up",
    "waiting": "the migrate job is queued on FC",
    "running": "FC is migrating the site",
    "success": "finished",
    "failure": "failed",
}
SKIP_WARNING = "FC continues past a failing patch. The site can end up with a partial migrate."


@dataclass(frozen=True)
class MigrateOptions:
    skip_failing_patches: bool = False
    confirm: str | None = None
    dry_run: bool = False
    no_wait: bool = False


def _scoped(err: FcmError, site: Site) -> FcmError:
    """Name the team (and its owner for a permission error), unless a site is the target."""
    if err.target and not err.target.startswith("team "):
        return err
    return explain_team_error(err, site.team)


def _patch_mode(plan: MigratePlan) -> str:
    return "Skip failing patches" if plan.skip_failing_patches else "Stop on a failing patch"


def _plan_json(s: Session, plan: MigratePlan) -> dict:
    site = plan.site
    return {
        "profile": s.profile.label,
        "team": {"name": site.team.name, "label": site.team.display, "owner": site.team.owner},
        "bench": {"name": site.bench, "title": site.bench_title},
        "site": site.name,
        "site_status": plan.status,
        "skip_failing_patches": plan.skip_failing_patches,
    }


def _state_json(state: MigrateState) -> dict:
    return {
        "stage": state.stage,
        "job": state.job or None,
        "status": state.status or None,
        "steps": [asdict(step) for step in state.steps],
        "site_status": state.site_status or None,
    }


def _preview(s: Session, plan: MigratePlan) -> None:
    site = plan.site
    s.out.message("")
    s.out.detail(
        "Migrate preview",
        [
            ("Profile", s.profile.label),
            ("Team", team_label(site.team)),
            ("Owner", site.team.owner or "unknown"),
            ("Bench", f"{site.bench_title} ({site.bench})"),
            ("Site", site.name),
            ("Site status", plan.status),
            ("Patches", _patch_mode(plan)),
            ("Action", "FC runs bench migrate on this site"),
        ],
    )
    if plan.skip_failing_patches:
        s.out.warning(SKIP_WARNING)
    s.out.message("")


def _confirm(s: Session, site: Site, confirm: str | None) -> None:
    if s.interactive:
        typed = picker.ask_text(f"Type the site name to migrate ({site.name}):")
        if typed != site.name:
            raise UsageError("Cancelled. Nothing was sent to FC.", target=f"site {site.name}")
        return
    if confirm != site.name:
        raise UsageError(
            f"The migrate needs --confirm {site.name}",
            target=f"site {site.name}",
            hint=f"Pass --confirm {site.name} after you check the preview (--dry-run).",
        )


def _stage(state: MigrateState) -> str:
    return STAGE_TEXT[state.stage]


def _table(state: MigrateState, running: dict[str, str] | None = None) -> Table:
    return steps_table(state.steps, running)


def watch_view(title: str, clock=time.monotonic) -> WatchView:
    """The live migrate screen (see cli/watch.py)."""
    return WatchView("Migrate", title, stage_text=_stage, table=_table, clock=clock)


def _watch(s: Session, service: MigrateService, plan: MigratePlan) -> MigrateState:
    final: MigrateState | None = None
    states = service.watch(plan, sleep=time.sleep)
    if s.out.json_mode:
        for state in changes(states):
            s.out.emit_json_line({"event": "progress", **_state_json(state)})
            final = state
    elif s.interactive:
        view = watch_view(plan.site.name)
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
            s.out.message(f"{STAGE_TEXT[state.stage]}{now}")
            final = state
    assert final is not None
    return final


def migrate_site(
    s: Session,
    site: Site,
    opts: MigrateOptions,
    *,
    in_menu: bool = False,
    path: str | None = None,
) -> None:
    """The work of `site-migrate` for a known site. The menu calls it too.

    Ctrl+C in the watch: exit 130, or WatchStopped in the menu."""
    json_mode = s.out.json_mode
    service = MigrateService(s.client)
    try:
        plan = service.check(site, skip_failing_patches=opts.skip_failing_patches)
    except FcmError as err:
        raise _scoped(err, site) from err

    if opts.dry_run:
        if json_mode:
            s.out.emit_json({"dry_run": True, "plan": _plan_json(s, plan)})
        else:
            _preview(s, plan)
            s.out.message("Dry run: nothing was sent to FC.")
        return

    if not json_mode:
        _preview(s, plan)
    _confirm(s, site, opts.confirm)

    try:
        service.start(plan)  # the only write
    except FcmError as err:
        raise _scoped(err, site) from err
    if json_mode:
        s.out.emit_json_line({"event": "accepted", "plan": _plan_json(s, plan)})
    else:
        s.out.message(f"FC accepted the migrate of {site.name}.")
    if opts.no_wait:
        s.out.message(f"The migrate started. Follow it with: fcm site-show {site.name}")
        return

    try:
        final = _watch(s, service, plan)
    except KeyboardInterrupt:
        s.out.message("")
        s.out.message(
            f"Stopped watching. The migrate continues on FC. Run: fcm site-show {site.name}"
        )
        if in_menu:
            raise WatchStopped from None
        raise typer.Exit(130) from None
    except FcmError as err:
        raise _scoped(err, site) from err

    if json_mode:
        s.out.emit_json_line({"event": "result", **_state_json(final)})
    else:
        s.out.message("")
        s.out.detail(
            "Migrate finished: the site is migrated",
            [
                ("Site", site.name),
                ("Job", final.job),
                ("Site status", final.site_status or "unknown"),
            ],
        )


@app.command("site-migrate", rich_help_panel="Site")
def site_migrate(
    site: Annotated[
        str | None,
        typer.Argument(help="Site name. Leave out on a terminal to pick team, bench, site."),
    ] = None,
    team: TeamOpt = None,
    skip_failing_patches: Annotated[
        bool,
        typer.Option("--skip-failing-patches", help="Let FC continue past a failing patch."),
    ] = False,
    confirm: Annotated[
        str | None,
        typer.Option("--confirm", help="Site name; required to migrate without a terminal."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Run the checks and show the preview only.")
    ] = False,
    no_wait: Annotated[
        bool, typer.Option("--no-wait", help="Return when FC accepts the migrate.")
    ] = False,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """Run bench migrate on one site. Shows a preview and asks for the site name."""
    interactive = picker.is_interactive(json_mode)
    if site is None and not interactive:
        raise UsageError("No site given", hint="Give the site: fcm site-migrate <site>")
    options = MigrateOptions(
        skip_failing_patches=skip_failing_patches,
        confirm=confirm,
        dry_run=dry_run,
        no_wait=no_wait,
    )
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        target = resolve_site(s, teams, site) if site else walk_to_site(s, teams)
        if not interactive and not dry_run and confirm != target.name:
            _confirm(s, target, confirm)  # raises before any check or write
        migrate_site(s, target, options)
