"""Shared CLI options and the per-command session."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated

import typer

from fc_manager import config, credentials
from fc_manager.api.client import FCClient
from fc_manager.cli import picker
from fc_manager.errors import FcmError, PartialFailure, PermissionDenied, UsageError
from fc_manager.inventory import Ambiguous, Fanout, Inventory, Missing, Resolved, Team, resolve
from fc_manager.output import Output

ProfileOpt = Annotated[
    str | None,
    typer.Option("--profile", help="Profile to use (default: FCM_PROFILE, then the default)."),
]
JsonOpt = Annotated[bool, typer.Option("--json", help="Write JSON to stdout. Never prompts.")]
DebugOpt = Annotated[
    bool, typer.Option("--debug", help="Show each FC request and full tracebacks on stderr.")
]
TeamOpt = Annotated[str | None, typer.Option("--team", help="Limit to one team (name or title).")]


@dataclass
class Session:
    out: Output
    client: FCClient
    inventory: Inventory
    profile: credentials.ActiveProfile
    interactive: bool


@contextmanager
def session(profile: str | None, json_mode: bool, debug: bool) -> Iterator[Session]:
    out = Output(json_mode=json_mode)
    active = credentials.resolve(profile, config.load())
    client = FCClient(
        active.credentials,
        active.base_url,
        profile=None if active.from_env else active.label,
        debug=out.debug if debug else None,
    )
    try:
        yield Session(
            out=out,
            client=client,
            inventory=Inventory(client),
            profile=active,
            interactive=picker.is_interactive(json_mode),
        )
    finally:
        client.close()


def target_path(s: Session, team: Team | None = None, bench=None, site=None) -> str:
    """The target path shown above each prompt: profile > team > bench > site."""
    parts = [s.profile.label]
    if team is not None:
        parts.append(team.display)
    if bench is not None:
        parts.append(f"{bench.title or bench.name} ({bench.name})")
    if site is not None:
        parts.append(site.name)
    return " > ".join(parts)


def team_label(team: Team) -> str:
    """Team for messages and pickers: its display label, plus the FC id when different."""
    return team.display if team.display == team.name else f"{team.display} ({team.name})"


def explain_team_error(err: FcmError, team: Team) -> FcmError:
    """Point a team-scoped error at the team label, and at the owner for permissions."""
    err.target = f"team {team_label(team)}"
    if isinstance(err, PermissionDenied):
        who = team.owner or "a team admin"
        err.hint = f"Your FC role in this team does not allow it. Ask {who} for access."
    return err


def scope_teams(s: Session, team_query: str | None) -> list[Team]:
    """All discovered teams, or the one team that --team names (name, owner or title)."""
    teams = s.inventory.teams()
    if not team_query:
        if not teams:
            raise UsageError(
                f"Profile {s.profile.label} has no teams on FC",
                hint="Check the account in the FC dashboard.",
            )
        return teams
    result = resolve(
        teams, team_query, name=lambda t: t.name, title=lambda t: t.title, alias=lambda t: t.owner
    )
    if isinstance(result, Resolved):
        return [result.item]
    if isinstance(result, Ambiguous):
        team = picker.pick_or_fail(
            interactive=s.interactive,
            prompt="Team",
            options=[(team_label(t), t) for t in result.candidates],
            problem=f"Team {team_query!r} matches {len(result.candidates)} teams",
        )
        return [team]
    assert isinstance(result, Missing)
    valid = ", ".join(team_label(t) for t in teams) or "none"
    raise UsageError(f"Team {team_query!r} not found", hint=f"Valid teams: {valid}")


def count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def teams_phrase(teams: list[Team]) -> str:
    if len(teams) == 1:
        return f"team {teams[0].display}"
    return count(len(teams), "team")


def raise_failures(fanout: Fanout, teams: list[Team]) -> None:
    """After rows are shown: raise the error for failed teams, if any."""
    if not fanout.failures:
        return
    if not fanout.rows and len(fanout.failures) == len(teams) == 1:
        team, err = fanout.failures[0]
        raise explain_team_error(err, team)
    failures: list[tuple[str, FcmError]] = [(team_label(t), err) for t, err in fanout.failures]
    if fanout.rows:
        message = f"{len(failures)} of {count(len(teams), 'team')} failed; other teams are shown"
    else:
        message = f"{len(failures)} of {count(len(teams), 'team')} failed; no results"
    raise PartialFailure(
        message,
        failures=failures,
        hint="Ask the owners of the failed teams for access, or limit the command with --team.",
    )
