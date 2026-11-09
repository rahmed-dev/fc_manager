"""site-update groups 4 and 5: `fcm site-update`, its walk, and the update watch screen."""

import json

import pytest
from rich.console import Console

from fc_manager.cli import picker
from fc_manager.cli import update as update_cli
from fc_manager.migrate import JobStep
from fc_manager.update import UpdateState

from .conftest import _site, save_profile

SITE = "erp.acme.example.com"
STEPS = ["Deactivate Site", "Backup Site", "Move Site", "Migrate Site", "Activate Site"]


def rec(status, steps=("Success",) * 5, recover_job=None, name="su-new") -> dict:
    return {
        "name": name,
        "status": status,
        "source_bench": "bench-1234-000001-f1",
        "destination_bench": "bench-1234-000002-f1",
        "recover_job": recover_job,
        "steps": [
            {"title": t, "status": st, "output": "patch x failed"}
            for t, st in zip(STEPS, steps, strict=False)
        ],
    }


@pytest.fixture
def ufc(env, fc, monkeypatch):
    """Fake FC with site erp.acme.example.com (bench-1234, team-acme, has an update)."""
    save_profile()
    fc.update_records = [
        rec("Running", ("Success", "Success", "Running", "Pending", "Pending")),
        rec("Success"),
    ]
    monkeypatch.setattr(update_cli.time, "sleep", lambda _s: None)
    return fc


def writes(fc) -> list[str]:
    return [m for m, _, verb in fc.teams_seen if verb == "POST"]


# --- 5.1 checks, preview, confirmation ------------------------------------------------


def test_dry_run_shows_preview_and_sends_nothing(ufc, cli):
    result = cli("site-update", SITE, "--dry-run")
    assert result.code == 0, result.err
    for text in ("Update preview", "work", "ACME Corp", "acme@example.com", "ACME Prod",
                 "bench-1234", SITE, "Active", "frappe  v16.1.0 -> v16.2.0",
                 "hrms  4444444 -> 5555555", update_cli.DOWNTIME, "Stop on a failing patch",
                 "the branch of hrms changes from version-15 to version-16",
                 "Dry run: nothing was sent to FC."):  # fmt: skip
        assert text in result.out, text
    assert "erpnext" not in result.out  # no update for erpnext
    assert "Warning" not in result.out
    assert writes(ufc) == []


def test_dry_run_with_skip_warns(ufc, cli):
    result = cli("site-update", SITE, "--dry-run", "--skip-failing-patches")
    assert result.code == 0, result.err
    assert "Skip failing patches" in result.out
    assert "FC continues past a failing patch" in result.out


def test_dry_run_json(ufc, cli):
    result = cli("site-update", SITE, "--dry-run", "--json")
    assert result.code == 0, result.err
    plan = json.loads(result.out)["plan"]
    assert plan["site"] == SITE
    assert [a["app"] for a in plan["apps"]] == ["frappe", "hrms"]
    assert plan["skip_backups"] is False


def test_no_update_exits_0_and_sends_nothing(ufc, cli):
    result = cli("site-update", "hr.acme.example.com", "--confirm", "hr.acme.example.com")
    assert result.code == 0, result.err
    assert "has no update" in result.out
    assert writes(ufc) == []


def test_skip_backups_is_not_an_option(ufc, cli):
    result = cli("site-update", SITE, "--skip-backups", "--dry-run")
    assert result.code == 2
    assert writes(ufc) == []


def test_script_needs_confirm(ufc, cli):
    result = cli("site-update", SITE, "--json")
    assert result.code == 2
    assert f"--confirm {SITE}" in json.loads(result.err)["error"]
    assert writes(ufc) == []


def test_script_wrong_confirm(ufc, cli):
    result = cli("site-update", SITE, "--confirm", "erp")
    assert result.code == 2
    assert writes(ufc) == []


def test_script_without_site(ufc, cli):
    result = cli("site-update", "--json")
    assert result.code == 2
    assert writes(ufc) == []
    assert not any(m.endswith("check_for_updates") for m in ufc.calls)


def test_status_check_refuses(ufc, cli):
    ufc.sites["team-acme"][0]["status"] = "Broken"
    result = cli("site-update", SITE, "--confirm", SITE)
    assert result.code == 2
    assert "Broken" in result.err
    assert writes(ufc) == []


def test_job_in_progress_refuses(ufc, cli):
    ufc.other_jobs = [{"name": "job-5", "job_type": "Backup Site", "status": "Running"}]
    result = cli("site-update", SITE, "--confirm", SITE)
    assert result.code == 2
    assert "Backup Site" in result.err
    assert writes(ufc) == []


def test_confirmed_update_success(ufc, cli):
    result = cli("site-update", SITE, "--confirm", SITE)
    assert result.code == 0, result.err
    assert ufc.update_posts == [
        {"name": SITE, "skip_failing_patches": False, "skip_backups": False}
    ]
    assert writes(ufc) == ["press.api.site.update"]
    assert "the site is updated" in result.out
    assert "bench-1234-000002-f1" in result.out


def test_skip_flag_reaches_fc(ufc, cli):
    result = cli("site-update", SITE, "--confirm", SITE, "--skip-failing-patches")
    assert result.code == 0, result.err
    assert ufc.update_posts[0]["skip_failing_patches"] is True
    assert ufc.update_posts[0]["skip_backups"] is False


def test_no_wait(ufc, cli):
    result = cli("site-update", SITE, "--confirm", SITE, "--no-wait")
    assert result.code == 0, result.err
    assert "The update started" in result.out
    assert f"fcm site-show {SITE}" in result.out
    assert ufc.teams_seen[-1][0] == "press.api.site.update"  # no watch read after the POST
    assert len(ufc.update_posts) == 1


FAILED = ("Success", "Success", "Success", "Failure", "Pending")


@pytest.mark.parametrize(
    "status,text",
    [
        ("Recovered", "FC restored the site to the old bench"),
        ("Fatal", "FC could not restore the site"),
        ("Cancelled", "The update was cancelled on FC"),
    ],
)
def test_failed_update_exits_8(ufc, cli, status, text):
    ufc.update_records = [rec("Failure", FAILED), rec(status, FAILED, recover_job="job-9")]
    result = cli("site-update", SITE, "--confirm", SITE)
    assert result.code == 8
    assert text in result.err
    if status != "Cancelled":
        assert "Migrate Site" in result.err
    if status == "Fatal":
        assert "FC support" in result.err
        assert "Site status on FC" in result.err
    assert len(ufc.update_posts) == 1


def test_missing_record_name_exits_6(ufc, cli):
    ufc.update_answer = None
    result = cli("site-update", SITE, "--confirm", SITE)
    assert result.code == 6
    assert "not known" in result.err
    assert f"fcm site-show {SITE}" in result.err
    assert len(ufc.update_posts) == 1


def test_write_unknown_names_site_show(ufc, cli):
    ufc.post_error = (502, {"exception": "bad gateway"})
    result = cli("site-update", SITE, "--confirm", SITE)
    assert result.code == 6
    assert "update request" in result.err
    assert f"fcm site-show {SITE}" in result.err
    assert len(ufc.update_posts) == 1


def test_json_events(ufc, cli):
    result = cli("site-update", SITE, "--confirm", SITE, "--json")
    assert result.code == 0, result.err
    lines = [json.loads(line) for line in result.out.splitlines()]
    assert lines[0]["event"] == "accepted"
    assert lines[0]["record"] == "su-new"
    assert lines[-1]["event"] == "result"
    assert lines[-1]["stage"] == "success"


def test_ctrl_c_during_watch(ufc, cli, monkeypatch):
    def interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(update_cli.time, "sleep", interrupt)
    result = cli("site-update", SITE, "--confirm", SITE)
    assert result.code == 130
    assert "The update continues on FC" in result.out
    assert len(ufc.update_posts) == 1


# --- 5.1 / 5.2 interactive, and the 4.1 site filter -----------------------------------


@pytest.fixture
def tty(monkeypatch):
    """Interactive mode with scripted answers for choose and ask_text."""
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    seen = {"choose": [], "text": []}
    answers = {"choose": [], "text": []}

    def choose(prompt, options, *, back=False, path=None, space_picks=False):
        seen["choose"].append(
            {"prompt": prompt, "options": options, "path": path, "space_picks": space_picks}
        )
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


def test_typed_site_name_sends_the_update(ufc, cli, tty):
    seen, answers = tty
    answers["text"] = [SITE]
    result = cli("site-update", SITE)
    assert result.code == 0, result.err
    assert seen["text"] == [f"Type the site name to update ({SITE}):"]
    assert len(ufc.update_posts) == 1


@pytest.mark.parametrize("typed", ["", "erp", "ACME Prod"])
def test_wrong_typed_name_cancels(ufc, cli, tty, typed):
    _, answers = tty
    answers["text"] = [typed]
    result = cli("site-update", SITE)
    assert result.code == 2
    assert "Cancelled. Nothing was sent to FC." in result.err
    assert writes(ufc) == []


def test_walk_one_site_with_an_update_is_picked_with_no_list(ufc, cli, tty):
    seen, answers = tty
    answers["choose"] = ["ACME Corp", "bench-1234"]
    answers["text"] = ["nope"]
    result = cli("site-update")
    assert result.code == 2
    assert [c["prompt"] for c in seen["choose"]] == ["Team", "Bench"]  # hr.acme has no update
    assert f"Site: {SITE}  (Active)" in result.out
    assert SITE in seen["text"][0]
    assert writes(ufc) == []


def test_walk_lists_only_sites_with_an_update(ufc, cli, tty):
    ufc.sites["team-acme"].append(
        _site("crm.acme.example.com", "team-acme", "bench-1234", "ACME Prod", update=True)
    )
    seen, answers = tty
    answers["choose"] = ["ACME Corp", "bench-1234", SITE]
    answers["text"] = ["nope"]
    result = cli("site-update")
    assert result.code == 2
    assert [c["prompt"] for c in seen["choose"]] == ["Team", "Bench", "Site"]
    site_step = seen["choose"][2]
    assert site_step["path"] == "work > ACME Corp > ACME Prod (bench-1234)"
    assert site_step["space_picks"] is True
    site_labels = [label for label, _ in site_step["options"]]
    assert site_labels == [f"{SITE}  (Active)", "crm.acme.example.com  (Active)"]
    assert writes(ufc) == []


def test_walk_bench_with_no_update_says_so_and_goes_back(ufc, cli, tty):
    seen, answers = tty
    answers["choose"] = ["ACME Corp", "bench-1240", "bench-1234"]
    answers["text"] = ["nope"]
    result = cli("site-update")
    assert result.code == 2
    assert "No site of bench Prod has an update." in result.out
    assert [c["prompt"] for c in seen["choose"]] == ["Team", "Bench", "Bench"]
    assert writes(ufc) == []


def test_migrate_walk_still_lists_every_site(ufc, cli, tty, monkeypatch):
    """The shared walk with no filter (site-migrate) is unchanged."""
    seen, answers = tty
    answers["choose"] = ["ACME Corp", "bench-1234", SITE]
    answers["text"] = ["nope"]
    cli("site-migrate")
    site_labels = [label for label, _ in seen["choose"][2]["options"]]
    assert site_labels == [f"{SITE}  (Active)", "hr.acme.example.com  (Inactive)"]


# --- update watch screen --------------------------------------------------------------


def _render(view) -> str:
    console = Console(width=200, record=True, color_system=None)
    console.print(view)
    return console.export_text()


def test_update_view_shows_steps_and_liveness():
    steps = (JobStep("Backup Site", "Success", ""), JobStep("Move Site", "Running", ""))
    now = [100.0]
    view = update_cli.watch_view(SITE, clock=lambda: now[0])
    view.update(UpdateState(stage="running", steps=steps, checked_at=100.0, polls=3))
    now[0] = 104.0
    text = _render(view)
    assert f"Update {SITE}: FC is updating the site - Move Site" in text
    assert "last FC answer 4 s ago (poll 3)" in text
    assert "running 4 s" in text


def test_update_view_recovering():
    view = update_cli.watch_view(SITE, clock=lambda: 0.0)
    view.update(UpdateState(stage="recovering", checked_at=0.0, polls=1))
    assert "FC restores the site to the old bench" in _render(view)
