"""`fcm site-update`: move one FC site to the newest bench of its bench group.

The walk is: site (or team, bench, a site with an update on a terminal), checks, preview,
typed site name, update request, watch of the update record, result. The only write is
the update request. There is no option to skip the FC backup.
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
from fc_manager.update import NothingToUpdate, UpdatePlan, UpdateService, UpdateState

STAGE_TEXT = {
    "waiting": "the update is queued on FC",
    "running": "FC is updating the site",
    "failure": "the update failed; waiting for FC to restore the site",
    "recovering": "FC restores the site to the old bench",
    "success": "finished",
    "recovered": "failed; FC restored the site to the old bench",
    "fatal": "failed; FC could not restore the site",
    "cancelled": "cancelled on FC",
}
SKIP_WARNING = "FC continues past a failing patch. The site can end up with a partial migrate."
DOWNTIME = "Site is down during the update; FC takes a backup first"
EMPTY_SITE_STEP = "No site of bench {bench} has an update."


def has_update(site: Site) -> bool:
    """The site filter of the update walk and the menu entry."""
    return site.update_available


@dataclass(frozen=True)
class UpdateOptions:
    skip_failing_patches: bool = False
    confirm: str | None = None
    dry_run: bool = False
    no_wait: bool = False


def _scoped(err: FcmError, site: Site) -> FcmError:
    """Name the team (and its owner for a permission error), unless a site is the target."""
    if err.target and not err.target.startswith("team "):
        return err
    return explain_team_error(err, site.team)


def _patch_mode(plan: UpdatePlan) -> str:
    return "Skip failing patches" if plan.skip_failing_patches else "Stop on a failing patch"


def _app_line(change) -> str:
    return f"{change.app}  {change.current_version} -> {change.next_version}"


def _plan_json(s: Session, plan: UpdatePlan) -> dict:
    site = plan.site
    return {
        "profile": s.profile.label,
        "team": {"name": site.team.name, "label": site.team.display, "owner": site.team.owner},
        "bench": {"name": site.bench, "title": site.bench_title},
        "site": site.name,
        "site_status": plan.status,
        "apps": [asdict(change) for change in plan.apps],
        "skip_failing_patches": plan.skip_failing_patches,
        "skip_backups": False,
    }


def _state_json(state: UpdateState) -> dict:
    return {
        "stage": state.stage,
        "record": state.record or None,
        "status": state.status or None,
        "steps": [asdict(step) for step in state.steps],
        "source_bench": state.source_bench or None,
        "destination_bench": state.destination_bench or None,
        "site_status": state.site_status or None,
    }


def _preview(s: Session, plan: UpdatePlan) -> None:
    site = plan.site
    apps = [_app_line(change) for change in plan.apps] or ["(FC lists no app change)"]
    rows = [
        ("Profile", s.profile.label),
        ("Team", team_label(site.team)),
        ("Owner", site.team.owner or "unknown"),
        ("Bench", f"{site.bench_title} ({site.bench})"),
        ("Site", site.name),
        ("Site status", plan.status),
        ("Apps", apps[0]),
        *[("", line) for line in apps[1:]],
        ("Patches", _patch_mode(plan)),
        ("Action", "FC moves the site to the newest bench of its bench group"),
        ("Downtime", DOWNTIME),
    ]
    s.out.message("")
    s.out.detail("Update preview", rows)
    for change in plan.apps:
        if change.branch_changes:
            s.out.message(
                f"Note: the branch of {change.app} changes from "
                f"{change.current_branch or 'unknown'} to {change.branch or 'unknown'}."
            )
    if plan.skip_failing_patches:
        s.out.warning(SKIP_WARNING)
    s.out.message("")


def _confirm(s: Session, site: Site, confirm: str | None) -> None:
    if s.interactive:
        typed = picker.ask_text(f"Type the site name to update ({site.name}):")
        if typed != site.name:
            raise UsageError("Cancelled. Nothing was sent to FC.", target=f"site {site.name}")
        return
    if confirm != site.name:
        raise UsageError(
            f"The update needs --confirm {site.name}",
            target=f"site {site.name}",
            hint=f"Pass --confirm {site.name} after you check the preview (--dry-run).",
        )


def _stage(state: UpdateState) -> str:
    return STAGE_TEXT.get(state.stage, state.stage)


def _table(state: UpdateState, running: dict[str, str] | None = None) -> Table:
    return steps_table(state.steps, running)


def watch_view(title: str, clock=time.monotonic) -> WatchView:
    """The live update screen (see cli/watch.py)."""
    return WatchView("Update", title, stage_text=_stage, table=_table, clock=clock)


def _watch(s: Session, service: UpdateService, plan: UpdatePlan, record: str) -> UpdateState:
    final: UpdateState | None = None
    states = service.watch(plan, record, sleep=time.sleep)
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
            s.out.message(f"{_stage(state)}{now}")
            final = state
    assert final is not None
    return final


def update_site(
    s: Session,
    site: Site,
    opts: UpdateOptions,
    *,
    in_menu: bool = False,
    path: str | None = None,
) -> None:
    """The work of `site-update` for a known site. The menu calls it too.

    No update: a message and a normal return (exit 0). Ctrl+C in the watch: exit 130, or
    WatchStopped in the menu."""
    json_mode = s.out.json_mode
    service = UpdateService(s.client)
    try:
        plan = service.check(site, skip_failing_patches=opts.skip_failing_patches)
    except NothingToUpdate:
        if json_mode:
            s.out.emit_json({"site": site.name, "update_available": False})
        else:
            s.out.message(f"Site {site.name} has no update. Nothing was sent to FC.")
        return
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
        record = service.start(plan)  # the only write
    except FcmError as err:
        raise _scoped(err, site) from err
    if json_mode:
        s.out.emit_json_line({"event": "accepted", "record": record, "plan": _plan_json(s, plan)})
    else:
        s.out.message(f"FC accepted the update of {site.name} ({record}).")
    if opts.no_wait:
        s.out.message(f"The update started. Follow it with: fcm site-show {site.name}")
        return

    try:
        final = _watch(s, service, plan, record)
    except KeyboardInterrupt:
        s.out.message("")
        s.out.message(
            f"Stopped watching. The update continues on FC. Run: fcm site-show {site.name}"
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
            "Update finished: the site is updated",
            [
                ("Site", site.name),
                ("New bench", final.destination_bench or "unknown"),
                ("Old bench", final.source_bench or "unknown"),
                ("Site status", final.site_status or "unknown"),
            ],
        )


@app.command("site-update", rich_help_panel="Site")
def site_update(
    site: Annotated[
        str | None,
        typer.Argument(
            help="Site name. Leave out on a terminal to pick team, bench, site with an update."
        ),
    ] = None,
    team: TeamOpt = None,
    skip_failing_patches: Annotated[
        bool,
        typer.Option("--skip-failing-patches", help="Let FC continue past a failing patch."),
    ] = False,
    confirm: Annotated[
        str | None,
        typer.Option("--confirm", help="Site name; required to update without a terminal."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Run the checks and show the preview only.")
    ] = False,
    no_wait: Annotated[
        bool, typer.Option("--no-wait", help="Return when FC accepts the update.")
    ] = False,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """Move one site to the newest bench of its group. Shows a preview and asks for the
    site name."""
    interactive = picker.is_interactive(json_mode)
    if site is None and not interactive:
        raise UsageError("No site given", hint="Give the site: fcm site-update <site>")
    options = UpdateOptions(
        skip_failing_patches=skip_failing_patches,
        confirm=confirm,
        dry_run=dry_run,
        no_wait=no_wait,
    )
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        if site:
            target = resolve_site(s, teams, site)
        else:
            target = walk_to_site(s, teams, only=has_update, empty=EMPTY_SITE_STEP)
        if not interactive and not dry_run and confirm != target.name:
            _confirm(s, target, confirm)  # raises before any check or write
        update_site(s, target, options)
