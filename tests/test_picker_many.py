"""bench-deploy 4.1: multi-select picker, Esc to go back, text prompt."""

import pytest
import questionary
from prompt_toolkit.keys import Keys

from fc_manager.cli import picker
from fc_manager.errors import UsageError


class FakeQuestion:
    def __init__(self, answer):
        self.answer = answer

    def ask(self):
        return self.answer


def capture(monkeypatch, answer, name="checkbox"):
    seen = {}

    def prompt(message, choices=None, **kwargs):
        seen.update(kwargs, message=message, choices=choices)
        return FakeQuestion(answer)

    monkeypatch.setattr(picker.questionary, name, prompt)
    return seen


def test_apps_open_all_selected(monkeypatch):
    seen = capture(monkeypatch, [0, 1])
    assert picker.choose_many("Apps", [("erpnext", "e"), ("hrms", "h")], selected=True) == [
        "e",
        "h",
    ]
    assert [c.checked for c in seen["choices"]] == [True, True]
    assert seen["use_search_filter"] is True


def test_sites_open_none_selected(monkeypatch):
    seen = capture(monkeypatch, [])
    assert picker.choose_many("Sites", [("a", 1), ("b", 2), ("c", 3)], selected=False) == []
    assert [c.checked for c in seen["choices"]] == [False, False, False]


def test_choose_many_cancel_exits_2(monkeypatch):
    capture(monkeypatch, None)
    with pytest.raises(UsageError) as info:
        picker.choose_many("Apps", [("a", 1)], selected=True)
    assert info.value.exit_code == 2


def test_choose_many_back_marker_raises_go_back(monkeypatch):
    capture(monkeypatch, picker._BACK)
    with pytest.raises(picker.GoBack):
        picker.choose_many("Sites", [("a", 1)], selected=False)


def test_choose_with_back(monkeypatch):
    capture(monkeypatch, picker._BACK, name="select")
    with pytest.raises(picker.GoBack):
        picker.choose("Bench", [("a", 1)], back=True)


def test_escape_is_bound_on_a_real_prompt():
    question = questionary.checkbox("Sites", choices=["a", "b"])
    before = len(question.application.key_bindings.bindings)
    picker._bind_back(question)
    bindings = question.application.key_bindings.bindings
    assert len(bindings) == before + 1
    assert bindings[-1].keys == (Keys.Escape,)


def test_ask_text_cancel_exits_2(monkeypatch):
    monkeypatch.setattr(picker.questionary, "text", lambda *a, **k: FakeQuestion(None))
    with pytest.raises(UsageError) as info:
        picker.ask_text("Type the bench title")
    assert info.value.exit_code == 2
    assert "Nothing was sent to FC" in info.value.message


def test_path_line_prints_above_the_prompt(monkeypatch):
    printed = []
    monkeypatch.setattr(picker.questionary, "print", lambda text, style=None: printed.append(text))

    class Question:
        def ask(self):
            printed.append("<prompt>")
            return 0

    monkeypatch.setattr(picker.questionary, "select", lambda *a, **k: Question())
    assert picker.choose("Action", [("Show", "show")], path="work > ACME > ACME Prod") == "show"
    assert printed == ["work > ACME > ACME Prod", "<prompt>"]
    printed.clear()
    picker.choose("Action", [("Show", "show")])
    assert printed == ["<prompt>"]


# --- picker-ux: style and Space in the site step ---------------------------------------


def test_both_pickers_use_the_readable_style(monkeypatch):
    seen = capture(monkeypatch, [0], name="checkbox")
    picker.choose_many("Apps", [("erpnext", "e")], selected=False)
    assert seen["style"] is picker.STYLE
    seen = capture(monkeypatch, 0, name="select")
    picker.choose("Site", [("a", 1)])
    assert seen["style"] is picker.STYLE
    rules = dict(picker.STYLE.style_rules)
    assert "noreverse" in rules["selected"]  # no grey reverse background on checked rows


def _run_select(monkeypatch, keys, **opts):
    """Run choose() on a real questionary select, fed by `keys`."""
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    real = questionary.select
    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        monkeypatch.setattr(
            picker.questionary,
            "select",
            lambda *a, **k: real(*a, **k, input=pipe, output=DummyOutput()),
        )
        return picker.choose("Site", [("erp.example.com", "erp"), ("crm.example.com", "crm")],
                             **opts)  # fmt: skip


def test_space_picks_the_row_under_the_pointer(monkeypatch):
    assert _run_select(monkeypatch, "\x1b[B ", space_picks=True) == "crm"


def test_space_is_not_bound_by_default(monkeypatch):
    question = questionary.select("Bench", choices=["a", "b"])
    before = len(question.application.key_bindings.bindings)
    picker._bind_space_picks(question)
    assert len(question.application.key_bindings.bindings) == before + 1
    monkeypatch.setattr(picker, "_bind_space_picks", lambda q: pytest.fail("Space bound"))
    seen = capture(monkeypatch, 0, name="select")
    picker.choose("Bench", [("a", 1)])
    assert "Enter to pick" in seen["instruction"] and "Space" not in seen["instruction"]


# --- add-app 9.5: the search prompt -------------------------------------------------------


def _fake_autocomplete(monkeypatch, typed: str, pick_row: int | None):
    """questionary.autocomplete stand-in: type `typed`, read the completer rows, and answer
    with row `pick_row` (or the typed text when None)."""
    from prompt_toolkit.document import Document

    from fc_manager.cli import picker

    seen = {}

    def autocomplete(message, *, choices, completer, style, key_bindings):
        rows = [c.text for c in completer.get_completions(Document(typed), None)]
        seen["rows"] = rows
        seen["message"] = message

        class _Q:
            def ask(self):
                return rows[pick_row] if pick_row is not None else typed

        return _Q()

    monkeypatch.setattr(picker.questionary, "autocomplete", autocomplete)
    return seen


def _find(text):
    from fc_manager.search import SearchIndex

    index = SearchIndex([f"app_{n:03}" for n in range(50)] + ["helpdesk"], key=lambda a: a)
    return [(item, item.upper()) for item in index.search(text)]


def test_search_prompt_shows_at_most_10_rows_and_picks_the_row(monkeypatch):
    from fc_manager.cli import picker

    seen = _fake_autocomplete(monkeypatch, "app", pick_row=2)
    assert picker.search("Search", _find) == "APP_002"
    assert len(seen["rows"]) == 10
    assert "type to search" in seen["message"]


def test_search_prompt_enter_on_text_picks_the_best_row(monkeypatch):
    from fc_manager.cli import picker

    _fake_autocomplete(monkeypatch, "hlpdsk", pick_row=None)
    assert picker.search("Search", _find) == "HELPDESK"
