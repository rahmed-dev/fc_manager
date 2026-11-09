"""Interactive picker for a missing or ambiguous target.

Interactive mode means: stdin and stdout are terminals and --json is not set. Outside
interactive mode the tool never prompts; it raises a usage error with the candidates.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import TypeVar

import questionary
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from fc_manager.errors import UsageError

T = TypeVar("T")

MAX_LISTED = 20

_BACK = object()

# Checked rows keep the normal background (the prompt_toolkit default for "selected" is
# reverse video, which is hard to read). ANSI names follow the terminal theme.
STYLE = questionary.Style(
    [
        ("selected", "noreverse fg:ansigreen"),
        ("highlighted", "bold"),
        ("pointer", "fg:ansicyan bold"),
    ]
)


class Cancelled(UsageError):
    """The user pressed Ctrl+C at a prompt (exit 2 in a direct command)."""


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


def _bind_space_picks(question) -> None:
    """Make Space pick the row under the pointer, as Enter does."""
    bindings = getattr(getattr(question, "application", None), "key_bindings", None)
    if bindings is None or not hasattr(bindings, "add"):
        return

    enter = bindings.get_bindings_for_keys((Keys.ControlM,))
    if not enter:
        return

    @bindings.add(" ", eager=True)
    def _pick(event) -> None:
        enter[-1].handler(event)  # the questionary Enter handler: pick and end


def is_interactive(json_mode: bool) -> bool:
    if json_mode:
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def show_path(path: str | None) -> None:
    """Print the target path (profile > team > bench) above a prompt."""
    if path:
        questionary.print(path, style="fg:ansibrightblack")


def choose(
    prompt: str,
    options: Sequence[tuple[str, T]],
    *,
    back: bool = False,
    path: str | None = None,
    space_picks: bool = False,
    disabled: Callable[[T], str | None] | None = None,
) -> T:
    """Show a type-to-filter list. Ctrl+C exits with code 2. With `back`, Esc raises GoBack.
    With `path`, the target path prints above the prompt. With `space_picks`, Space picks
    the row under the pointer, as Enter does (only for lists whose labels hold no space).
    With `disabled`, a row whose value gets a reason is shown with that reason and cannot
    be picked. At least one row must stay pickable."""
    choices = [
        questionary.Choice(title=label, value=index, disabled=disabled(value) if disabled else None)
        for index, (label, value) in enumerate(options)
    ]
    keys = "Enter or Space to pick" if space_picks else "Enter to pick"
    if back:
        keys += ", Esc to go back"
    question = questionary.select(
        prompt,
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        instruction=f"(type to filter, {keys}, Ctrl+C to cancel)",
        style=STYLE,
    )
    if back:
        _bind_back(question)
    if space_picks:
        _bind_space_picks(question)
    show_path(path)
    answer = question.ask()
    if answer is _BACK:
        raise GoBack
    if answer is None:
        raise Cancelled("Cancelled, nothing done")
    return options[answer][1]


def choose_many(
    prompt: str,
    options: Sequence[tuple[str, T]],
    *,
    selected: bool,
    back: bool = True,
    path: str | None = None,
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
        style=STYLE,
    )
    if back:
        _bind_back(question)
    show_path(path)
    answer = question.ask()
    if answer is _BACK:
        raise GoBack
    if answer is None:
        raise Cancelled("Cancelled, nothing done")
    return [options[index][1] for index in answer]


def search(
    prompt: str,
    find: Callable[[str], Sequence[tuple[str, T]]],
    *,
    back: bool = False,
    path: str | None = None,
) -> T:
    """A search prompt: as the user types, `find(text)` gives the rows to show (the caller
    keeps it to at most 10, best first). Enter on a row picks it. Enter on typed text picks
    the best row for that text. With `back`, Esc raises GoBack. Ctrl+C exits with code 2.

    `find` runs locally on every key press, so it must not send a request."""
    seen: dict[str, T] = {}

    class _Rows(Completer):
        def get_completions(self, document, complete_event):
            for label, value in find(document.text):
                seen[label] = value
                yield Completion(label, start_position=-len(document.text))

    bindings = KeyBindings()
    if back:

        @bindings.add("escape", eager=True)
        def _back(event) -> None:
            event.app.exit(result=_BACK)

    keys = "type to search, Tab or arrows to move, Enter to pick" + (
        ", Esc to go back" if back else ""
    )
    show_path(path)
    while True:
        question = questionary.autocomplete(
            f"{prompt} ({keys}, Ctrl+C to cancel)",
            choices=[],
            completer=_Rows(),
            style=STYLE,
            key_bindings=bindings,
        )
        answer = question.ask()
        if answer is _BACK:
            raise GoBack
        if answer is None:
            raise Cancelled("Cancelled, nothing done")
        if answer in seen:
            return seen[answer]
        rows = find(answer)
        if rows:
            return rows[0][1]
        print("No match. Type a part of the name.")


def ask_yes_no(prompt: str, *, default: bool = False) -> bool:
    """Ask a yes or no question. Esc and Ctrl+C mean no."""
    question = questionary.confirm(prompt, default=default, style=STYLE)
    _bind_back(question)
    answer = question.ask()
    return answer is True


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
