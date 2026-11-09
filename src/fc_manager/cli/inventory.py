"""`fcm team ...`, `fcm bench ...`, `fcm site ...`: read-only inventory commands."""

from __future__ import annotations

from dataclasses import asdict
from enum import StrEnum
from typing import Annotated

import typer

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
    teams_phrase,
)
from fc_manager.cli.root import app
from fc_manager.errors import NotFound, PermissionDenied, UsageError
from fc_manager.inventory import Ambiguous, Bench, Fanout, Resolved, Site, resolve
from fc_manager.output import Column


class SiteStatus(StrEnum):
    active = "active"
    inactive = "inactive"
    broken = "broken"
    trial = "trial"
    update_available = "update-available"


def _team_json(team) -> dict:
    return {"name": team.name, "title": team.title, "owner": team.owner, "label": team.display}


def _bench_label(bench: Bench) -> str:
    return f"{bench.title} ({bench.name})  - {bench.team.display}"


def _site_label(site: Site) -> str:
    return f"{site.name}  - {site.team.display} / {site.bench_title or site.bench}"


def _show_partial_site(s: Session, site: Site, json_mode: bool) -> None:
    """FC listed the site but denied its detail: show what the site list already gave."""
    if json_mode:
        data = _site_json(site)
        data.update(server=None, apps=None, detail="not_permitted")
        s.out.emit_json(data)
        return
    s.out.detail(
        f"Site {site.name}",
        [
            ("Team", team_label(site.team)),
            ("Bench", f"{site.bench_title} ({site.bench})"),
            ("Status", site.status),
            ("Version", site.version),
            ("Region", site.region),
            ("Update", "available" if site.update_available else "none"),
            ("Details", "not permitted for your role in this team"),
        ],
    )


# --- team -----------------------------------------------------------------------------


@app.command("team-list", rich_help_panel="Team")
def team_list(profile: ProfileOpt = None, json_mode: JsonOpt = False, debug: DebugOpt = False):
    """List every team that the profile can reach."""
    with session(profile, json_mode, debug) as s:
        teams = s.inventory.teams()
        s.out.table(
            [
                Column("Team", lambda t: t.name),
                Column("Title", lambda t: t.title),
                Column("Owner", lambda t: t.owner),
            ],
            teams,
            json_rows=[_team_json(t) for t in teams],
            summary=f"{count(len(teams), 'team')} for profile {s.profile.label}",
            empty=f"Profile {s.profile.label} has no teams on FC.",
        )


# --- bench ----------------------------------------------------------------------------


BENCH_COLUMNS = [
    Column("Team", lambda b: b.team.display),
    Column("Name", lambda b: b.name),
    Column("Title", lambda b: b.title),
    Column("Version", lambda b: b.version),
    Column("Status", lambda b: b.status),
    Column("Sites", lambda b: b.sites),
    Column("Apps", lambda b: b.apps),
]


def _bench_json(bench: Bench) -> dict:
    data = asdict(bench)
    data["team"] = _team_json(bench.team)
    return data


@app.command("bench-list", rich_help_panel="Bench")
def bench_list(
    team: TeamOpt = None,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """List benches in all teams, or in one team with --team."""
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        result = s.inventory.benches(teams)
        s.out.table(
            BENCH_COLUMNS,
            result.rows,
            json_rows=[_bench_json(b) for b in result.rows],
            summary=f"{count(len(result.rows), 'bench', 'benches')} in {teams_phrase(teams)}",
            empty=f"No benches found in {teams_phrase(teams)}.",
        )
        raise_failures(result, teams)


# --- site -----------------------------------------------------------------------------


SITE_COLUMNS = [
    Column("Team", lambda x: x.team.display),
    Column("Site", lambda x: x.name),
    Column("Bench", lambda x: x.bench_title or x.bench),
    Column("Status", lambda x: x.status),
    Column("Version", lambda x: x.version),
    Column("Region", lambda x: x.region),
    Column("Update", lambda x: "available" if x.update_available else ""),
]


def _site_json(site: Site) -> dict:
    data = asdict(site)
    data["team"] = _team_json(site.team)
    return data


def _resolve_bench(s: Session, teams, query: str) -> Bench | None:
    """Return the bench named by --bench, or None when a team failure hides it."""
    benches = s.inventory.benches(teams)
    result = resolve(benches.rows, query, name=lambda b: b.name, title=lambda b: b.title)
    exact_name = isinstance(result, Resolved) and result.item.name == query
    if benches.failures and not exact_name:
        # A failed team can hide a bench with the same title. Never guess the target.
        raise_failures(Fanout(rows=[], failures=benches.failures), teams)
    if isinstance(result, Resolved):
        return result.item
    if isinstance(result, Ambiguous):
        return picker.pick_or_fail(
            interactive=s.interactive,
            prompt="Bench",
            options=[(_bench_label(b), b) for b in result.candidates],
            problem=f"Bench {query!r} matches {len(result.candidates)} benches",
        )
    close = ", ".join(_bench_label(b) for b in result.close_matches)
    raise NotFound(
        f"Bench {query!r} not found in {teams_phrase(teams)}",
        hint=f"Close matches: {close}" if close else "Run: fcm bench-list",
    )


def _match_site(s: Session, result: Fanout[Site], teams, query: str) -> Site:
    """The site named `query` in the listed sites, or a pick when it matches several."""
    found = resolve(result.rows, query, name=lambda x: x.name, title=lambda x: x.name)
    if isinstance(found, Resolved):
        return found.item
    if isinstance(found, Ambiguous):
        return picker.pick_or_fail(
            interactive=s.interactive,
            prompt="Site",
            options=[(_site_label(x), x) for x in found.candidates],
            problem=f"Site {query!r} matches {len(found.candidates)} sites",
        )
    if result.failures:
        raise_failures(result, teams)
    close = ", ".join(x.name for x in found.close_matches)
    raise NotFound(
        f"Site {query} not found in {teams_phrase(teams)}",
        hint=f"Close matches: {close}" if close else "Run: fcm site-list",
    )


def resolve_site(s: Session, teams, query: str) -> Site:
    """The site from its name (or a unique part of it), as `fcm site-show` finds it."""
    return _match_site(s, s.inventory.sites(teams), teams, query)


def choose_site(s: Session, bench: Bench, *, back: bool, path: str | None = None) -> Site | None:
    """The site step: one site of `bench`, picked from the sites of that bench only.
    Returns None when the bench has no site. Esc raises picker.GoBack when `back`."""
    result = s.inventory.sites([bench.team])
    if result.failures:
        raise_failures(result, [bench.team])
    rows = [x for x in result.rows if x.bench == bench.name]
    if not rows:
        s.out.message(f"Bench {bench.title or bench.name} has no site.")
        return None
    return picker.choose(
        "Site", [(f"{x.name}  ({x.status})", x) for x in rows], back=back, path=path
    )


@app.command("site-list", rich_help_panel="Site")
def site_list(
    team: TeamOpt = None,
    bench: Annotated[
        str | None, typer.Option("--bench", help="Only sites on this bench (name or title).")
    ] = None,
    status: Annotated[
        SiteStatus | None, typer.Option("--status", help="Only sites with this status.")
    ] = None,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """List sites in all teams, or narrow them with --team, --bench and --status."""
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        bench_filter = _resolve_bench(s, teams, bench) if bench else None
        if bench_filter is not None:
            teams = [bench_filter.team]
        result = s.inventory.sites(teams, status=status.value if status else None)
        rows = result.rows
        where = teams_phrase(teams)
        if bench_filter is not None:
            rows = [site for site in rows if site.bench == bench_filter.name]
            where = f"bench {bench_filter.title or bench_filter.name}"
        s.out.table(
            SITE_COLUMNS,
            rows,
            json_rows=[_site_json(x) for x in rows],
            summary=f"{count(len(rows), 'site')} in {where}",
            empty=f"No sites found in {where}.",
        )
        raise_failures(result, teams)


@app.command("site-show", rich_help_panel="Site")
def site_show(
    site: Annotated[
        str | None,
        typer.Argument(help="Site name. Leave out on a terminal to pick from a list."),
    ] = None,
    team: TeamOpt = None,
    profile: ProfileOpt = None,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
):
    """Show one site with its installed apps."""
    if site is None and not picker.is_interactive(json_mode):
        raise UsageError("No site given", hint="Give the site name: fcm site-show <site>")
    with session(profile, json_mode, debug) as s:
        teams = scope_teams(s, team)
        result = s.inventory.sites(teams)
        sites = result.rows

        if site is None:
            if not sites:
                raise_failures(result, teams)
                raise NotFound(f"No sites found in {teams_phrase(teams)}")
            target = picker.pick_or_fail(
                interactive=s.interactive,
                prompt="Site",
                options=[(_site_label(x), x) for x in sites],
                problem="No site given",
            )
        else:
            target = _match_site(s, result, teams, site)

        try:
            detail = s.inventory.site_detail(target)
        except PermissionDenied as err:
            _show_partial_site(s, target, json_mode)
            raise explain_team_error(
                PermissionDenied(
                    f"Details and apps of {target.name} are not permitted for your role "
                    f"in team {target.team.display}",
                    server_message=err.server_message,
                ),
                target.team,
            ) from err
        if json_mode:
            data = _site_json(detail.site)
            data.update(
                server=detail.server,
                version=detail.version,
                apps=[asdict(a) for a in detail.apps],
            )
            s.out.emit_json(data)
            return
        s.out.detail(
            f"Site {target.name}",
            [
                ("Team", team_label(target.team)),
                ("Bench", f"{target.bench_title} ({target.bench})"),
                ("Status", target.status),
                ("Version", detail.version),
                ("Region", target.region),
                ("Server", detail.server),
                ("Update", "available" if target.update_available else "none"),
            ],
        )
        s.out.message("")
        s.out.table(
            [
                Column("App", lambda a: a.name),
                Column("Title", lambda a: a.title),
                Column("Branch", lambda a: a.branch),
                Column("Repository", lambda a: a.repository),
                Column("Commit", lambda a: a.hash),
            ],
            detail.apps,
            json_rows=[],
            summary=f"{count(len(detail.apps), 'app')} installed",
            empty="No installed apps reported by FC.",
        )
