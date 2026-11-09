"""Entry point of `fcm` and the top-level error handler. Commands live in cli/root.py."""

from __future__ import annotations

import sys
import traceback

import typer

from fc_manager.cli import deploy, inventory, menu, migrate, profile  # noqa: F401 - register commands
from fc_manager.cli.root import NOUNS, READ_VERBS, WRITE_VERBS, app  # noqa: F401 - public names
from fc_manager.errors import FcmError, UsageError
from fc_manager.output import Output


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
