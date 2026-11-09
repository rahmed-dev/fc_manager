"""Interactive picker for a missing or ambiguous target.

Interactive mode means: stdin and stdout are terminals and --json is not set. Outside
interactive mode the tool never prompts; it raises a usage error with the candidates.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TypeVar

import questionary

from fc_manager.errors import UsageError

T = TypeVar("T")

MAX_LISTED = 20


def is_interactive(json_mode: bool) -> bool:
    if json_mode:
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def choose(prompt: str, options: Sequence[tuple[str, T]]) -> T:
    """Show a type-to-filter list. Cancel (Esc / Ctrl+C) exits with code 2."""
    choices = [
        questionary.Choice(title=label, value=index) for index, (label, _) in enumerate(options)
    ]
    answer = questionary.select(
        prompt,
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        instruction="(type to filter, Enter to pick, Ctrl+C to cancel)",
    ).ask()
    if answer is None:
        raise UsageError("Cancelled, nothing done")
    return options[answer][1]


def pick_or_fail(
    *,
    interactive: bool,
    prompt: str,
    options: Sequence[tuple[str, T]],
    problem: str,
    hint: str | None = None,
) -> T:
    """Prompt in interactive mode; else raise a usage error that lists the candidates."""
    if interactive and options:
        return choose(prompt, options)
    if options:
        listed = [label for label, _ in options[:MAX_LISTED]]
        more = len(options) - len(listed)
        candidates = "; ".join(listed) + (f"; and {more} more" if more > 0 else "")
        hint = f"Candidates: {candidates}" + (f". {hint}" if hint else "")
    raise UsageError(problem, hint=hint)
