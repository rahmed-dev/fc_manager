"""Root `fcm` group. Every command registers here with its full hyphenated name.

Grammar: fcm <noun>-<verb> [TARGET] [options]. A space always separates the command word
from an argument or an option. Nouns are singular. No aliases.
"""

from __future__ import annotations

import typer
from typer.core import TyperGroup

from fc_manager.errors import UsageError

NOUNS = ("profile", "team", "bench", "site")
READ_VERBS = frozenset({"list", "show", "add", "remove", "test"})
# Each write verb previews and asks for a typed confirmation.
WRITE_VERBS = frozenset({"deploy", "migrate", "update"})
PLURALS = {"profiles": "profile", "teams": "team", "benches": "bench", "sites": "site"}
PANELS = {noun: noun.capitalize() for noun in NOUNS}


class FcmGroup(TyperGroup):
    """Root group: turns a plural noun or an old two-word form into a usage error that
    names the hyphenated command. Runs before any session opens, so nothing reaches FC."""

    def resolve_command(self, ctx: typer.Context, args: list[str]):
        if args and args[0] in PLURALS:
            singular = PLURALS[args[0]]
            raise UsageError(
                f"No command '{args[0]}': nouns are singular",
                hint=f"Use: fcm {singular}-list",
            )
        if args and args[0] in NOUNS:
            noun = args[0]
            if len(args) > 1 and f"{noun}-{args[1]}" in self.commands:
                raise UsageError(
                    f"No command '{noun} {args[1]}': commands are one word",
                    hint=f"Use: fcm {noun}-{args[1]}",
                )
            names = [name for name in self.list_commands(ctx) if name.startswith(f"{noun}-")]
            raise UsageError(
                f"No command '{noun}': commands are one word",
                hint="Use one of: " + ", ".join(f"fcm {name}" for name in names),
            )
        return super().resolve_command(ctx, args)


app = typer.Typer(
    cls=FcmGroup,
    no_args_is_help=False,  # `fcm` alone opens the menu on a terminal (cli/menu.py)
    add_completion=False,
    help="Explore Frappe Cloud teams, benches and sites, and deploy app updates to a bench.",
    pretty_exceptions_enable=False,
)
