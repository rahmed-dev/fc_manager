"""The live watch screen for an FC job (deploy, migrate).

The status line is built again at each screen refresh, so "last FC answer N s ago" grows
when a poll hangs, even while no new state arrives. That makes the screen report the true
state of the watch, not only show motion.

A state must give: `steps` (each with `label` and `status`), `current_step`, `final`,
`checked_at` (clock time of the last FC answer) and `polls`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from rich.console import Group
from rich.markup import escape
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

STALE_SECONDS = 10.0  # no FC answer for this long: the status line turns yellow


def seconds(value: float) -> str:
    value = int(value)
    return f"{value // 60}m{value % 60:02d}s" if value >= 60 else f"{value} s"


def duration(value: str) -> str:
    """FC gives some durations as bare seconds ("15.8"). Add the unit."""
    try:
        float(value)
    except ValueError:
        return value
    return f"{value} s"


def steps_table(
    steps: Iterable[Any],
    running: dict[str, str] | None = None,
    status_text: Callable[[Any], str] = lambda step: step.status,
) -> Table:
    """`running` maps a step label to the time text to show for a running step."""
    table = Table(show_edge=False, pad_edge=False, header_style="bold")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Time")
    for step in steps:
        time_text = (running or {}).get(step.label, duration(step.duration))
        table.add_row(escape(step.label), escape(status_text(step)), escape(time_text))
    return table


def changes(states: Iterable[Any]) -> Iterator[Any]:
    """Only the states with new FC data (a watch yields one per poll)."""
    last = None
    for state in states:
        if state != last:
            last = state
            yield state


class WatchView:
    """`kind` is the job word ("Deploy", "Migrate"). `stage_text(state)` gives the stage
    line, `table(state, running)` the steps table, and `footer(state)` an optional line
    under the table."""

    def __init__(
        self,
        kind: str,
        title: str,
        *,
        stage_text: Callable[[Any], str],
        table: Callable[[Any, dict[str, str]], Table],
        footer: Callable[[Any], str | None] = lambda _state: None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.kind = kind
        self.title = title
        self.stage_text = stage_text
        self.table = table
        self.footer = footer
        self.clock = clock
        self.started = clock()
        self.state: Any = None
        self.running_since: dict[str, float] = {}  # step label -> first poll that saw Running
        self.spinner = Spinner("dots")
        self.done = False

    def update(self, state: Any) -> None:
        self.state = state
        for step in state.steps:
            if step.status == "Running":
                self.running_since.setdefault(step.label, state.checked_at or self.clock())

    def status_line(self) -> Text:
        now = self.clock()
        state = self.state
        stage = self.stage_text(state) if state else "sending the first poll to FC"
        step = state.current_step if state and not state.final else None
        line = Text.assemble(
            (f"{self.kind} ", "bold"),
            (self.title, "bold"),
            f": {stage}",
            f" - {step.label}" if step else "",
        )
        line.append(f"\n  elapsed {seconds(now - self.started)}")
        if self.done:
            return line
        last = state.checked_at if state else self.started
        age = now - last
        if age >= STALE_SECONDS:
            line.append(f"  |  no answer from FC for {seconds(age)}", style="yellow")
        else:
            polls = state.polls if state else 0
            line.append(f"  |  last FC answer {seconds(age)} ago (poll {polls})")
        return line

    def __rich__(self):
        running = {}
        if self.state and not self.done:
            now = self.clock()
            running = {
                step.label: f"running {seconds(now - self.running_since[step.label])}"
                for step in self.state.steps
                if step.status == "Running" and step.label in self.running_since
            }
        parts = []
        if self.state:
            parts.append(self.table(self.state, running))
            footer = self.footer(self.state)
            if footer:
                parts.append(Text(footer))
        if self.done:
            return Group(self.status_line(), *parts)
        self.spinner.update(text=self.status_line())
        return Group(self.spinner, *parts)
