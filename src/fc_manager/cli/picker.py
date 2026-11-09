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

_BACK = object()


class GoBack(Exception):  # noqa: N818 - a signal, not an error
    """The user pressed Esc to go back one step of a walk."""


def _bind_back(question) -> None:
    """Make Esc end the prompt with the _BACK marker."""
    bindings = getattr(getattr(question, "application", None), "key_bindings", None)
    if bindings is None or not hasattr(bindings, "add"):
        return

    @bindings.add("escape", eager=True)
    def _back(event) -> None:
        event.app.exit(result=_BACK)


def is_interactive(json_mode: bool) -> bool:
    if json_mode:
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def choose(prompt: str, options: Sequence[tuple[str, T]], *, back: bool = False) -> T:
    """Show a type-to-filter list. Ctrl+C exits with code 2. With `back`, Esc raises GoBack."""
    choices = [
        questionary.Choice(title=label, value=index) for index, (label, _) in enumerate(options)
    ]
    keys = "Enter to pick, Esc to go back" if back else "Enter to pick"
    question = questionary.select(
        prompt,
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        instruction=f"(type to filter, {keys}, Ctrl+C to cancel)",
    )
    if back:
        _bind_back(question)
    answer = question.ask()
    if answer is _BACK:
        raise GoBack
    if answer is None:
        raise UsageError("Cancelled, nothing done")
    return options[answer][1]


def choose_many(
    prompt: str,
    options: Sequence[tuple[str, T]],
    *,
    selected: bool,
    back: bool = True,
) -> list[T]:
    """Show a multi-select list. `selected` sets the default of every option.

    Space toggles, Enter confirms, Esc raises GoBack (with `back`), Ctrl+C exits with 2."""
    choices = [
        questionary.Choice(title=label, value=index, checked=selected)
        for index, (label, _) in enumerate(options)
    ]
    keys = "Space to toggle, Enter to confirm" + (", Esc to go back" if back else "")
    question = questionary.checkbox(
        prompt,
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        instruction=f"({keys}, Ctrl+C to cancel)",
    )
    if back:
        _bind_back(question)
    answer = question.ask()
    if answer is _BACK:
        raise GoBack
    if answer is None:
        raise UsageError("Cancelled, nothing done")
    return [options[index][1] for index in answer]


def ask_text(prompt: str) -> str:
    """Ask for one line of text. Ctrl+C exits with code 2."""
    answer = questionary.text(prompt).ask()
    if answer is None:
        raise UsageError("Cancelled. Nothing was sent to FC.")
    return answer


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
