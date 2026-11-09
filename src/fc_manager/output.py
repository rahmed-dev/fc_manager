"""Everything the user sees goes through this module.

Table mode: aligned tables on stdout, errors on stderr. Rich turns color off when the
stream is not a terminal or when NO_COLOR is set.
JSON mode: stdout holds only JSON data; errors are one JSON object on stderr.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TextIO

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from fc_manager.errors import FcmError, PartialFailure
from fc_manager.redact import redact


@dataclass(frozen=True)
class Column:
    header: str
    get: Callable[[Any], Any]


def _isatty(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _cell(value: Any) -> str:
    if value is None or value is False:
        return ""
    if value is True:
        return "yes"
    return str(value)


class Output:
    def __init__(
        self,
        *,
        json_mode: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.json_mode = json_mode
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr
        # When stdout is not a terminal, never truncate cells: pipes must get full names.
        width = None if _isatty(self._stdout) else 1000
        self.console = Console(file=self._stdout, highlight=False, soft_wrap=False, width=width)
        self.err_console = Console(file=self._stderr, highlight=False, soft_wrap=True)

    # --- data -----------------------------------------------------------------------

    def emit_json(self, data: Any) -> None:
        self._stdout.write(json.dumps(data, indent=2, default=str) + "\n")
        self._stdout.flush()

    def emit_json_line(self, data: Any) -> None:
        """One compact JSON object per line (a stream, for example deploy progress)."""
        self._stdout.write(json.dumps(data, default=str) + "\n")
        self._stdout.flush()

    def table(
        self,
        columns: Sequence[Column],
        rows: Sequence[Any],
        *,
        json_rows: list[dict[str, Any]],
        summary: str,
        empty: str,
    ) -> None:
        if self.json_mode:
            self.emit_json(json_rows)
            return
        if not rows:
            self.console.print(escape(empty))
            return
        table = Table(show_edge=False, pad_edge=False, header_style="bold")
        for column in columns:
            table.add_column(column.header)
        for row in rows:
            table.add_row(*(escape(_cell(column.get(row))) for column in columns))
        self.console.print(table)
        self.console.print(escape(summary), style="dim")

    def detail(self, title: str, fields: Sequence[tuple[str, Any]]) -> None:
        """Key/value block for one item (table mode only)."""
        self.console.print(escape(title), style="bold")
        width = max((len(label) for label, _ in fields), default=0)
        for label, value in fields:
            self.console.print(f"  {escape(label.ljust(width))}  {escape(_cell(value))}")

    def message(self, text: str) -> None:
        if self.json_mode:
            return
        self.console.print(escape(text))

    def debug(self, line: str) -> None:
        self.err_console.print(escape(redact(line)), style="dim")

    # --- errors ---------------------------------------------------------------------

    def error(self, err: FcmError) -> None:
        if self.json_mode:
            payload: dict[str, Any] = {
                "error": redact(err.message),
                "kind": str(err.kind),
                "hint": redact(err.hint) if err.hint else None,
                "target": err.target,
            }
            if err.server_message:
                payload["server_message"] = redact(err.server_message)
            if isinstance(err, PartialFailure):
                payload["failures"] = [
                    {"team": team, "kind": str(e.kind), "error": redact(e.message)}
                    for team, e in err.failures
                ]
            self._stderr.write(json.dumps(payload) + "\n")
            self._stderr.flush()
            return

        lines = [f"[bold red]Error:[/] {escape(redact(err.message))}"]
        if err.target:
            lines.append(f"  Target: {escape(err.target)}")
        if err.server_message:
            lines.append(f"  FC says: {escape(redact(err.server_message))}")
        if isinstance(err, PartialFailure):
            for team, failure in err.failures:
                detail = failure.message
                if failure.server_message:
                    detail += f" - {failure.server_message}"
                lines.append(f"  Failed team {escape(team)}: {escape(redact(detail))}")
        if err.hint:
            lines.append(f"  Hint: {escape(redact(err.hint))}")
        self.err_console.print("\n".join(lines))

    def traceback(self, text: str) -> None:
        self.err_console.print(escape(redact(text)), style="dim")
