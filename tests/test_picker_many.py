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
