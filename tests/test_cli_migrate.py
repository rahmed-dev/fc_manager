"""site-migrate groups 4 and 5: `fcm site-migrate` and the migrate watch screen."""

import json

import pytest
from rich.console import Console

from fc_manager import migrate as migrate_module
from fc_manager.cli import migrate as migrate_cli
from fc_manager.cli import picker
from fc_manager.migrate import JobStep, MigrateState

from .conftest import save_profile

SITE = "erp.acme.example.com"


def job(status, steps=("Success",), name="job-new") -> dict:
    labels = ["Backup Site", "Migrate Site", "Activate Site"]
    return {
        "name": name,
        "status": status,
        "steps": [
            {"step_name": label, "status": st, "duration": "2", "output": "patch x failed"}
            for label, st in zip(labels, steps, strict=False)
        ],
    }


@pytest.fixture
def mfc(env, fc, monkeypatch):
    """Fake FC with site erp.acme.example.com (bench-1234, team-acme), no real sleeping."""
    save_profile()
    fc.job_docs = [
        job("Running", ("Success", "Running", "Pending")),
        job("Success", ("Success", "Success", "Success")),
    ]
    monkeypatch.setattr(migrate_cli.time, "sleep", lambda _s: None)
    return fc


def writes(fc) -> list[str]:
    return [m for m, _, verb in fc.teams_seen if verb == "POST"]


# --- 5.1 checks, preview, confirmation ------------------------------------------------


def test_dry_run_shows_preview_and_sends_nothing(mfc, cli):
    result = cli("site-migrate", SITE, "--dry-run")
    assert result.code == 0, result.err
    for text in ("Migrate preview", "work", "ACME Corp", "acme@example.com", "ACME Prod",
                 "bench-1234", SITE, "Active", "Stop on a failing patch",
                 "Dry run: nothing was sent to FC."):  # fmt: skip
        assert text in result.out, text
    assert "Warning" not in result.out
    assert writes(mfc) == []


def test_dry_run_with_skip_warns(mfc, cli):
    result = cli("site-migrate", SITE, "--dry-run", "--skip-failing-patches")
    assert result.code == 0, result.err
    assert "Skip failing patches" in result.out
    assert "FC continues past a failing patch" in result.out


def test_dry_run_json(mfc, cli):
    result = cli("site-migrate", SITE, "--dry-run", "--json")
    assert result.code == 0, result.err
    plan = json.loads(result.out)["plan"]
    assert plan["site"] == SITE
    assert plan["team"]["name"] == "team-acme"
    assert plan["skip_failing_patches"] is False


def test_script_needs_confirm(mfc, cli):
    result = cli("site-migrate", SITE, "--json")
    assert result.code == 2
    assert f"--confirm {SITE}" in json.loads(result.err)["error"]
    assert writes(mfc) == []


def test_script_wrong_confirm(mfc, cli):
    result = cli("site-migrate", SITE, "--confirm", "hr.acme.example.com")
    assert result.code == 2
    assert writes(mfc) == []


def test_script_without_site(mfc, cli):
    result = cli("site-migrate", "--json")
    assert result.code == 2
    assert mfc.teams_seen == []


def test_status_check_refuses(mfc, cli):
    mfc.sites["team-acme"][0]["status"] = "Suspended"
    result = cli("site-migrate", SITE, "--confirm", SITE)
    assert result.code == 2
    assert "Suspended" in result.err
    assert writes(mfc) == []


def test_job_in_progress_refuses(mfc, cli):
    mfc.other_jobs = [{"name": "j-1", "job_type": "Backup Site", "status": "Running"}]
    result = cli("site-migrate", SITE, "--confirm", SITE)
    assert result.code == 2
    assert "Backup Site" in result.err
    assert writes(mfc) == []


# --- 5.1 request, watch, result -------------------------------------------------------


def test_confirmed_migrate_success(mfc, cli):
    result = cli("site-migrate", SITE, "--confirm", SITE)
    assert result.code == 0, result.err
    assert mfc.migrate_posts == [{"name": SITE, "skip_failing_patches": False}]
    assert writes(mfc) == ["press.api.site.migrate"]
    assert "FC is migrating the site - Migrate Site" in result.out
    assert "the site is migrated" in result.out
    assert "job-new" in result.out
    for method, team, _ in mfc.teams_seen:
        if method != "press.api.site.all":  # the site lookup reads every team
            assert team == "team-acme", method


def test_skip_flag_reaches_fc(mfc, cli):
    result = cli("site-migrate", SITE, "--confirm", SITE, "--skip-failing-patches")
    assert result.code == 0, result.err
    assert mfc.migrate_posts == [{"name": SITE, "skip_failing_patches": True}]


def test_no_wait(mfc, cli):
    result = cli("site-migrate", SITE, "--confirm", SITE, "--no-wait")
    assert result.code == 0, result.err
    assert "The migrate started" in result.out
    assert f"fcm site-show {SITE}" in result.out
    assert "press.api.site.job" not in mfc.calls


def test_failure_exits_8(mfc, cli):
    mfc.job_docs = [job("Failure", ("Success", "Failure", "Pending"))]
    mfc.sites["team-acme"][0]["status"] = "Active"
    result = cli("site-migrate", SITE, "--confirm", SITE)
    assert result.code == 8
    assert "Migrate Site" in result.err
    assert len(mfc.migrate_posts) == 1


def test_job_not_found_exits_6(mfc, cli, monkeypatch):
    monkeypatch.setattr(migrate_module, "FIND_LIMIT_SECONDS", 0)
    mfc.migrate_makes_job = False
    result = cli("site-migrate", SITE, "--confirm", SITE)
    assert result.code == 6
    assert "not known" in result.err
    assert len(mfc.migrate_posts) == 1


def test_json_events(mfc, cli):
    result = cli("site-migrate", SITE, "--confirm", SITE, "--json")
    assert result.code == 0, result.err
    events = [json.loads(line)["event"] for line in result.out.splitlines()]
    assert events[0] == "accepted"
    assert events[-1] == "result"
    assert json.loads(result.out.splitlines()[-1])["stage"] == "success"


def test_write_unknown_names_site_show(mfc, cli):
    mfc.post_error = (502, {"exception": "bad gateway"})
    result = cli("site-migrate", SITE, "--confirm", SITE)
    assert result.code == 6
    assert "not known" in result.err
    assert f"fcm site-show {SITE}" in result.err
    assert len(mfc.migrate_posts) == 1


def test_ctrl_c_during_watch(mfc, cli, monkeypatch):
    def interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(migrate_cli.time, "sleep", interrupt)
    result = cli("site-migrate", SITE, "--confirm", SITE)
    assert result.code == 130
    assert "The migrate continues on FC" in result.out
    assert len(mfc.migrate_posts) == 1


# --- 5.1 / 5.2 interactive ------------------------------------------------------------


@pytest.fixture
def tty(monkeypatch):
    """Interactive mode with scripted answers for choose and ask_text."""
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    seen = {"choose": [], "text": []}
    answers = {"choose": [], "text": []}

    def choose(prompt, options, *, back=False, path=None):
        seen["choose"].append({"prompt": prompt, "options": options, "path": path})
        answer = answers["choose"].pop(0)
        if answer is picker.GoBack:
            raise picker.GoBack
        return next(value for label, value in options if answer in label)

    def ask_text(prompt):
        seen["text"].append(prompt)
        return answers["text"].pop(0)

    monkeypatch.setattr(picker, "choose", choose)
    monkeypatch.setattr(picker, "ask_text", ask_text)
    return seen, answers


def test_typed_site_name_sends_the_migrate(mfc, cli, tty):
    seen, answers = tty
    answers["text"] = [SITE]
    result = cli("site-migrate", SITE)
    assert result.code == 0, result.err
    assert seen["text"] == [f"Type the site name to migrate ({SITE}):"]
    assert len(mfc.migrate_posts) == 1


@pytest.mark.parametrize("typed", ["", "erp", "ACME Prod"])
def test_wrong_typed_name_cancels(mfc, cli, tty, typed):
    _, answers = tty
    answers["text"] = [typed]
    result = cli("site-migrate", SITE)
    assert result.code == 2
    assert "Cancelled. Nothing was sent to FC." in result.err
    assert writes(mfc) == []


def test_walk_team_bench_site_with_path(mfc, cli, tty):
    seen, answers = tty
    answers["choose"] = ["ACME Corp", "bench-1234", SITE]
    answers["text"] = ["nope"]
    result = cli("site-migrate")
    assert result.code == 2
    assert [c["prompt"] for c in seen["choose"]] == ["Team", "Bench", "Site"]
    assert [c["path"] for c in seen["choose"]] == [
        "work",
        "work > ACME Corp",
        "work > ACME Corp > ACME Prod (bench-1234)",
    ]
    site_labels = [label for label, _ in seen["choose"][2]["options"]]
    assert site_labels == [f"{SITE}  (Active)", "hr.acme.example.com  (Inactive)"]
    assert writes(mfc) == []


def test_walk_esc_at_site_goes_back_to_bench(mfc, cli, tty):
    seen, answers = tty
    answers["choose"] = ["ACME Corp", "bench-1234", picker.GoBack, "bench-1240", "stage"]
    answers["text"] = ["nope"]
    result = cli("site-migrate")
    assert result.code == 2
    assert [c["prompt"] for c in seen["choose"]] == ["Team", "Bench", "Site", "Bench", "Site"]
    assert "stage.acme.example.com" in seen["text"][0]


# --- 4.1 migrate watch screen ---------------------------------------------------------


def _render(view) -> str:
    console = Console(width=200, record=True, color_system=None)
    console.print(view)
    return console.export_text()


def _state(at, polls):
    steps = (JobStep("Backup Site", "Success", "26"), JobStep("Migrate Site", "Running", ""))
    return MigrateState(stage="running", job="job-new", status="Running", steps=steps,
                        checked_at=at, polls=polls)  # fmt: skip


def test_migrate_view_status_line():
    now = [100.0]
    view = migrate_cli.watch_view(SITE, clock=lambda: now[0])
    view.update(_state(100.0, 1))
    now[0] = 102.0
    view.update(_state(102.0, 2))
    now[0] = 104.0
    text = _render(view)
    assert f"Migrate {SITE}: FC is migrating the site - Migrate Site" in text
    assert "last FC answer 2 s ago (poll 2)" in text
    assert "running 4 s" in text
    assert "26 s" in text


def test_migrate_view_warns_when_fc_does_not_answer():
    now = [100.0]
    view = migrate_cli.watch_view(SITE, clock=lambda: now[0])
    view.update(_state(100.0, 1))
    now[0] = 112.0
    text = _render(view)
    assert "no answer from FC for 12 s" in text
    assert "last FC answer" not in text


def test_migrate_view_before_first_answer():
    view = migrate_cli.watch_view(SITE, clock=lambda: 5.0)
    assert "sending the first poll to FC" in _render(view)
