"""Root `fcm` command and the top-level error handler.

Grammar: fcm <noun> <verb> [TARGET] [options]. Nouns are singular. No aliases.
"""

from __future__ import annotations

import sys
import traceback

import typer
from typer.core import TyperGroup

from fc_manager.cli import deploy, inventory, profile  # noqa: F401 - deploy registers bench commands
from fc_manager.errors import FcmError, UsageError
from fc_manager.output import Output

NOUNS = ("profile", "team", "bench", "site")
READ_VERBS = frozenset({"list", "show", "add", "remove", "test"})
WRITE_VERBS = frozenset({"deploy"})  # each one previews and asks for a typed confirmation
PLURALS = {"profiles": "profile", "teams": "team", "benches": "bench", "sites": "site"}


class FcmGroup(TyperGroup):
    """Root group: turns a plural noun into a usage error with the right command."""

    def resolve_command(self, ctx: typer.Context, args: list[str]):
        if args and args[0] in PLURALS:
            singular = PLURALS[args[0]]
            raise UsageError(
                f"No command '{args[0]}': nouns are singular",
                hint=f"Use: fcm {singular} list",
            )
        return super().resolve_command(ctx, args)


app = typer.Typer(
    cls=FcmGroup,
    no_args_is_help=True,
    add_completion=False,
    help="Explore Frappe Cloud teams, benches and sites, and deploy app updates to a bench.",
    pretty_exceptions_enable=False,
)
app.add_typer(profile.app, name="profile")
app.add_typer(inventory.team_app, name="team")
app.add_typer(inventory.bench_app, name="bench")  # list (inventory), show and deploy (deploy)
app.add_typer(inventory.site_app, name="site")


def run(args: list[str]) -> int:
    """Run the CLI and return the exit code. Every error ends here."""
    json_mode = "--json" in args
    debug = "--debug" in args
    out = Output(json_mode=json_mode)
    command = typer.main.get_command(app)
    try:
        result = command.main(args=args, prog_name="fcm", standalone_mode=False)
        return result if isinstance(result, int) else 0
    except FcmError as err:
        out.error(err)
        return err.exit_code
    except typer.Exit as exc:
        return exc.exit_code
    except typer.Abort:
        out.error(UsageError("Cancelled, nothing done"))
        return 130
    except typer.TyperException as exc:  # usage errors from argument parsing
        show = getattr(exc, "show", None)
        if json_mode or show is None:
            out.error(UsageError(exc.format_message()))
        else:
            show(file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        out.error(UsageError("Cancelled, nothing done"))
        return 130
    except Exception as exc:  # noqa: BLE001 - last-resort handler, output is redacted
        out.error(
            FcmError(
                f"Unexpected error: {type(exc).__name__}: {exc}",
                hint=None if debug else "Run again with --debug to see the traceback.",
            )
        )
        if debug:
            out.traceback(traceback.format_exc())
        return 1


def main() -> None:
    sys.exit(run(sys.argv[1:]))
