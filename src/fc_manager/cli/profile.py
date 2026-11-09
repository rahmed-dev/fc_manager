"""`fcm profile ...`: local credential profiles."""

from __future__ import annotations

import re
from typing import Annotated

import typer

from fc_manager import config, credentials
from fc_manager.api.client import DEFAULT_BASE_URL, FCClient, validate_base_url
from fc_manager.cli import picker
from fc_manager.cli.common import DebugOpt, JsonOpt, count, team_label
from fc_manager.errors import UsageError
from fc_manager.inventory import Inventory
from fc_manager.output import Column, Output
from fc_manager.redact import Credentials

app = typer.Typer(no_args_is_help=True, help="Manage FC credential profiles (one per FC login).")

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

NameArg = Annotated[str, typer.Argument(help="Profile name, for example: work")]


def _prompt_key() -> str:
    return typer.prompt("FC API key")


def _prompt_secret() -> str:
    return typer.prompt("FC API secret (hidden)", hide_input=True)


def _confirm(question: str) -> bool:
    return typer.confirm(question, default=False)


def _check_name(name: str) -> None:
    if not NAME_RE.match(name):
        raise UsageError(
            f"Profile name {name!r} is not valid",
            hint="Use letters, digits, '.', '_' or '-' (max 64 characters).",
        )


def _require_profile(cfg: config.Config, name: str) -> config.Profile:
    if name not in cfg.profiles:
        known = ", ".join(sorted(cfg.profiles)) or "none"
        raise UsageError(f"Profile {name} does not exist (profiles: {known})")
    return cfg.profiles[name]


@app.command("add")
def add(
    name: NameArg,
    base_url: Annotated[
        str, typer.Option("--base-url", help="FC base URL (HTTPS only).")
    ] = DEFAULT_BASE_URL,
    replace: Annotated[
        bool, typer.Option("--replace", help="Replace the credentials of an existing profile.")
    ] = False,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
) -> None:
    """Add a profile. Reads the API secret from a hidden prompt and checks it with FC."""
    out = Output(json_mode=json_mode)
    _check_name(name)
    base_url = validate_base_url(base_url)
    cfg = config.load()
    if name in cfg.profiles and not replace:
        raise UsageError(
            f"Profile {name} already exists",
            hint=f"To change its credentials, run: fcm profile add {name} --replace",
        )
    if not credentials.keyring_usable():
        raise UsageError(
            "No secure OS keyring is available on this host", hint=credentials.ENV_HINT
        )
    if not picker.is_interactive(json_mode):
        raise UsageError(
            "fcm profile add needs a terminal to read the secret",
            hint="Run it in a terminal without --json. " + credentials.ENV_HINT,
        )

    creds = Credentials(_prompt_key().strip(), _prompt_secret().strip())
    if not creds.api_key or not creds.api_secret:
        raise UsageError("The API key and the API secret must not be empty")

    with FCClient(creds, base_url, profile=name, debug=out.debug if debug else None) as client:
        account = Inventory(client).account()

    credentials.store(name, creds)
    cfg.profiles[name] = config.Profile(name=name, base_url=base_url)
    if not cfg.default_profile:
        cfg.default_profile = name
    config.save(cfg)

    if json_mode:
        out.emit_json({"profile": name, "user": account.user, "teams": len(account.teams)})
    else:
        out.message(
            f"Profile {name} saved: user {account.user}, {count(len(account.teams), 'team')} found."
        )


@app.command("list")
def list_(json_mode: JsonOpt = False, debug: DebugOpt = False) -> None:
    """List profiles. Never shows keys or secrets."""
    out = Output(json_mode=json_mode)
    cfg = config.load()
    profiles = sorted(cfg.profiles.values(), key=lambda p: p.name)
    out.table(
        [
            Column("Profile", lambda p: p.name),
            Column("Default", lambda p: "*" if p.name == cfg.default_profile else ""),
            Column("Base URL", lambda p: p.base_url),
        ],
        profiles,
        json_rows=[
            {"name": p.name, "default": p.name == cfg.default_profile, "base_url": p.base_url}
            for p in profiles
        ],
        summary=count(len(profiles), "profile"),
        empty="No profiles. Run: fcm profile add <name>",
    )


@app.command("test")
def test(name: NameArg, json_mode: JsonOpt = False, debug: DebugOpt = False) -> None:
    """Check a stored profile against FC and show the teams it reaches."""
    out = Output(json_mode=json_mode)
    profile = _require_profile(config.load(), name)
    creds = credentials.load(name)
    with FCClient(
        creds, profile.base_url, profile=name, debug=out.debug if debug else None
    ) as client:
        account = Inventory(client).account()
    if json_mode:
        out.emit_json(
            {
                "profile": name,
                "user": account.user,
                "teams": [{"name": t.name, "title": t.title} for t in account.teams],
            }
        )
        return
    out.message(f"Profile {name} OK: user {account.user}")
    for team in account.teams:
        out.message(f"  {team_label(team)}")


@app.command("remove")
def remove(
    name: NameArg,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
    json_mode: JsonOpt = False,
    debug: DebugOpt = False,
) -> None:
    """Remove a profile and delete its keyring entry."""
    out = Output(json_mode=json_mode)
    cfg = config.load()
    _require_profile(cfg, name)
    if not yes:
        if not picker.is_interactive(json_mode):
            raise UsageError(
                f"Removing profile {name} needs confirmation", hint="Pass --yes to confirm."
            )
        if not _confirm(f"Remove profile {name} and delete its keyring entry?"):
            out.message("Cancelled, nothing changed.")
            return
    credentials.delete(name)
    del cfg.profiles[name]
    if cfg.default_profile == name:
        cfg.default_profile = min(cfg.profiles) if cfg.profiles else None
    config.save(cfg)
    if json_mode:
        out.emit_json({"removed": name, "default_profile": cfg.default_profile})
    else:
        out.message(f"Profile {name} removed.")
