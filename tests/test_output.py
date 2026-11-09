import io
import json
import re

from fc_manager.errors import AuthError, NotFound, PartialFailure, PermissionDenied
from fc_manager.output import Column, Output

ANSI = re.compile(r"\x1b\[")

COLUMNS = [Column("Name", lambda r: r["name"]), Column("Flag", lambda r: r["flag"])]
ROWS = [{"name": "a", "flag": True}, {"name": "b", "flag": None}]


def make(json_mode=False):
    out, err = io.StringIO(), io.StringIO()
    return Output(json_mode=json_mode, stdout=out, stderr=err), out, err


def test_table_mode_prints_headers_rows_and_summary():
    o, out, _ = make()
    o.table(COLUMNS, ROWS, json_rows=ROWS, summary="2 things in 1 team", empty="none")
    text = out.getvalue()
    assert "Name" in text and "Flag" in text and "a" in text and "yes" in text
    assert text.strip().endswith("2 things in 1 team")


def test_empty_result_prints_message_not_table():
    o, out, _ = make()
    o.table(COLUMNS, [], json_rows=[], summary="", empty="No sites found in team acme")
    assert out.getvalue().strip() == "No sites found in team acme"


def test_json_mode_writes_only_json():
    o, out, _ = make(json_mode=True)
    o.table(COLUMNS, ROWS, json_rows=ROWS, summary="x", empty="y")
    o.message("this must not appear")
    assert json.loads(out.getvalue()) == ROWS


def test_piped_output_has_no_ansi_codes(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    o, out, err = make()
    o.table(COLUMNS, ROWS, json_rows=ROWS, summary="2", empty="")
    o.error(AuthError("bad", hint="h"))
    assert not ANSI.search(out.getvalue())
    assert not ANSI.search(err.getvalue())


def test_long_cells_are_not_truncated_when_piped():
    o, out, _ = make()
    name = "a-very-long-site-name-" * 8 + ".example.com"
    o.table(COLUMNS, [{"name": name, "flag": False}], json_rows=[], summary="1", empty="")
    assert name in out.getvalue()


def test_error_table_mode_shows_target_server_message_and_hint():
    o, _, err = make()
    o.error(
        PermissionDenied("Permission denied", target="team acme", hint="Ask", server_message="No")
    )
    text = err.getvalue()
    assert "Error: Permission denied" in text
    assert "Target: team acme" in text
    assert "FC says: No" in text
    assert "Hint: Ask" in text


def test_error_json_mode_has_error_kind_hint():
    o, out, err = make(json_mode=True)
    o.error(NotFound("Site x not found", hint="Run: fcm site-list"))
    payload = json.loads(err.getvalue())
    assert payload["error"] == "Site x not found"
    assert payload["kind"] == "not_found"
    assert payload["hint"] == "Run: fcm site-list"
    assert out.getvalue() == ""


def test_partial_failure_lists_failed_teams():
    o, _, err = make(json_mode=True)
    o.error(PartialFailure("1 of 3 failed", failures=[("Beta", PermissionDenied("denied"))]))
    payload = json.loads(err.getvalue())
    assert payload["failures"] == [{"team": "Beta", "kind": "permission", "error": "denied"}]
