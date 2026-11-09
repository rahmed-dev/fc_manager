"""add-app group 4: `fcm bench-add-app` and `fcm site-install-app`."""

import json

import pytest

from fc_manager import migrate as migrate_module
from fc_manager.cli import apps as apps_cli
from fc_manager.cli import picker

from .conftest import save_profile

BENCH = "bench-1234"
SITE = "erp.acme.example.com"


def job(status, step_status, name="job-new") -> dict:
    return {
        "name": name,
        "status": status,
        "steps": [{"step_name": "Install App on Site", "status": step_status, "duration": "4",
                   "output": "app x failed"}],
    }  # fmt: skip


@pytest.fixture
def afc(env, fc, monkeypatch):
    save_profile()
    fc.job_docs = [job("Running", "Running"), job("Success", "Success")]
    monkeypatch.setattr(apps_cli.time, "sleep", lambda _s: None)
    return fc


def writes(fc) -> list[str]:
    return [m for m, _, verb in fc.teams_seen if verb == "POST"]


@pytest.fixture
def tty(monkeypatch):
    """Interactive mode with scripted answers for choose, ask_text and ask_yes_no."""
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    seen = {"choose": [], "text": []}
    answers = {"choose": [], "text": []}

    def choose(prompt, options, *, back=False, path=None, space_picks=False, disabled=None):
        notes = {label: disabled(value) for label, value in options} if disabled else {}
        seen["choose"].append({"prompt": prompt, "options": options, "notes": notes,
                               "back": back})  # fmt: skip
        answer = answers["choose"].pop(0)
        if answer is picker.GoBack:
            raise picker.GoBack
        label, value = next((lb, v) for lb, v in options if answer in lb)
        assert not notes.get(label), f"picked a disabled row: {label}"
        return value

    def ask_text(prompt):
        seen["text"].append(prompt)
        return answers["text"].pop(0)

    monkeypatch.setattr(picker, "choose", choose)
    monkeypatch.setattr(picker, "ask_text", ask_text)
    return seen, answers


# --- 4.1 / 9.5 bench-add-app ----------------------------------------------------------


@pytest.fixture
def search(monkeypatch):
    """Scripted picker.search and ask_yes_no. Each search answer is typed text: the test
    records the rows that the prompt would show and picks the first one."""
    shown, typed, more = [], [], []

    def fake_search(prompt, find, *, back=False, path=None):
        text = typed.pop(0)
        if text is picker.GoBack:
            raise picker.GoBack
        rows = find(text)
        shown.append({"prompt": prompt, "text": text, "rows": [label for label, _ in rows]})
        return rows[0][1]

    monkeypatch.setattr(picker, "search", fake_search)
    monkeypatch.setattr(picker, "ask_yes_no", lambda prompt, default=False: more.pop(0))
    return shown, typed, more


def test_add_dry_run_preview(afc, cli):
    result = cli("bench-add-app", BENCH, "--app", "crm", "--dry-run")
    assert result.code == 0, result.err
    for text in ("Add-app preview", "work", "ACME Corp", "acme@example.com", "ACME Prod",
                 BENCH, "Version 15", "Marketplace", "Frappe CRM (crm), main, frappe/crm",
                 "next deploy", "Dry run: nothing was sent to FC."):  # fmt: skip
        assert text in result.out, text
    assert writes(afc) == []


def test_add_dry_run_json(afc, cli):
    result = cli("bench-add-app", BENCH, "--app", "crm", "--dry-run", "--json")
    assert result.code == 0, result.err
    plan = json.loads(result.out)["plan"]
    assert plan["source"] == "marketplace"
    assert plan["apps"] == [{"name": "crm", "title": "Frappe CRM", "source": "src-crm",
                             "branch": "main", "repository": "frappe/crm"}]  # fmt: skip


def test_add_two_apps_in_one_post(afc, cli):
    result = cli(
        "bench-add-app", BENCH, "--app", "crm", "--app", "lms", "--source", "lms=src-lms-2",
        "--confirm", BENCH,
    )  # fmt: skip
    assert result.code == 0, result.err
    assert afc.add_posts == [{"name": BENCH, "apps": [
        {"app": "crm", "source": "src-crm"}, {"app": "lms", "source": "src-lms-2"}]}]  # fmt: skip
    assert writes(afc) == ["press.api.bench.add_apps"]
    assert "FC added crm, lms to bench ACME Prod." in result.out
    assert f"fcm bench-deploy {BENCH}" in result.out
    for method, team, _ in afc.teams_seen:
        if method != "press.api.bench.all":  # the bench lookup reads every team
            assert team == "team-acme", method


@pytest.mark.parametrize(
    "args",
    [
        ("bench-add-app", BENCH, "--app", "crm", "--json"),
        ("bench-add-app", BENCH, "--app", "crm", "--confirm", "ACME Prod"),
        ("bench-add-app", BENCH, "--json"),
        ("bench-add-app", "--app", "crm", "--json"),
        ("bench-add-app", BENCH, "--app", "crm", "--repo", "https://github.com/a/b"),
        ("bench-add-app", BENCH, "--app", "crm", "--source", "nonsense", "--confirm", BENCH),
        ("bench-add-app", BENCH, "--repo", "https://github.com/acme/x", "--confirm", BENCH),
    ],
)
def test_add_script_refusals(afc, cli, args):
    result = cli(*args)
    assert result.code == 2
    assert writes(afc) == []


def test_add_script_needs_confirm_message(afc, cli):
    result = cli("bench-add-app", BENCH, "--app", "crm", "--json")
    assert f"--confirm {BENCH}" in json.loads(result.err)["error"]


def test_add_no_bench_in_a_script_sends_nothing(afc, cli):
    result = cli("bench-add-app", "--app", "crm")
    assert result.code == 2
    assert afc.teams_seen == []


@pytest.mark.parametrize("app", ["missing", "old"])
def test_add_app_not_offered_or_not_compatible(afc, cli, app):
    result = cli("bench-add-app", BENCH, "--app", app, "--confirm", BENCH)
    assert result.code == 2
    assert app in result.err
    assert writes(afc) == []


def test_add_several_sources_in_a_script(afc, cli):
    result = cli("bench-add-app", BENCH, "--app", "lms", "--confirm", BENCH, "--json")
    assert result.code == 2
    error = json.loads(result.err)
    assert "2 sources" in error["error"]
    assert "--source lms=<source>" in error["hint"]
    assert "main" in error["hint"] and "develop" in error["hint"]
    assert writes(afc) == []


def test_add_unknown_answer_exits_6(afc, cli):
    afc.post_error = (502, {"message": "bad gateway"})
    result = cli("bench-add-app", BENCH, "--app", "crm", "--confirm", BENCH)
    assert result.code == 6
    assert f"fcm bench-show {BENCH}" in result.err
    assert len(afc.add_posts) == 1


def test_add_source_choice_then_market_search(afc, cli, tty, search):
    seen, answers = tty
    shown, typed, more = search
    answers["choose"] = ["marketplace"]
    typed += ["crm"]
    more += [False]
    answers["text"] = ["ACME Prod"]
    result = cli("bench-add-app", BENCH)
    assert result.code == 0, result.err
    assert [label for label, _ in seen["choose"][0]["options"]] == [
        "From the marketplace (search)", "From GitHub",
    ]  # fmt: skip
    assert shown[0]["rows"][0] == "Frappe CRM (crm)"
    assert "Old App (old)" not in shown[0]["rows"]  # not compatible: never offered
    assert seen["text"] == ["Type the bench title to add the app (ACME Prod):"]
    assert afc.add_posts == [{"name": BENCH, "apps": [{"app": "crm", "source": "src-crm"}]}]


def test_add_search_two_apps_and_source_step(afc, cli, tty, search):
    seen, answers = tty
    shown, typed, more = search
    answers["choose"] = ["marketplace", "develop"]  # source step for lms
    typed += ["crm", "lms"]
    more += [True, False]
    answers["text"] = ["ACME Prod"]
    result = cli("bench-add-app", BENCH)
    assert result.code == 0, result.err
    assert "Frappe CRM (crm)" not in shown[1]["rows"]  # an app already picked is left out
    assert "Picked: crm, lms" in result.out
    assert seen["choose"][1]["prompt"] == "Source of lms"
    assert afc.add_posts == [{"name": BENCH, "apps": [
        {"app": "crm", "source": "src-crm"}, {"app": "lms", "source": "src-lms-2"}]}]  # fmt: skip


def test_add_all_apps_read_once_in_a_session(afc, cli, tty, search):
    _, answers = tty
    _, typed, more = search
    answers["choose"] = ["marketplace"]
    typed += ["fr", "crm"]
    more += [True, False]
    answers["text"] = ["nope"]
    cli("bench-add-app", BENCH)
    assert afc.calls.count("press.api.bench.all_apps") == 1


@pytest.mark.parametrize("typed_title", ["", "bench", BENCH])
def test_add_wrong_title_cancels(afc, cli, tty, search, typed_title):
    _, answers = tty
    _, typed, more = search
    answers["choose"] = ["marketplace"]
    typed += ["crm"]
    more += [False]
    answers["text"] = [typed_title]
    result = cli("bench-add-app", BENCH)
    assert result.code == 2
    assert "Cancelled. Nothing was sent to FC." in result.err
    assert writes(afc) == []


def test_add_nothing_in_the_marketplace(afc, cli, tty, search):
    _, answers = tty
    afc.market_apps = [{"app": "old", "title": "Old", "sources": []}]
    answers["choose"] = ["marketplace"]
    result = cli("bench-add-app", BENCH)
    assert result.code == 2
    assert "No marketplace app can be added to bench ACME Prod" in result.err
    assert writes(afc) == []


# --- 9.5 GitHub -------------------------------------------------------------------------


def test_add_github_installed_repo(afc, cli, tty, search):
    seen, answers = tty
    shown, typed, _ = search
    answers["choose"] = ["From GitHub", "acme/acme_tools"]
    typed += [""]  # Enter with no text: the default branch
    answers["text"] = ["ACME Prod"]
    result = cli("bench-add-app", BENCH)
    assert result.code == 0, result.err
    repo_labels = [label for label, _ in seen["choose"][1]["options"]]
    assert repo_labels == ["acme/acme_theme", "acme/acme_tools", "Paste a public GitHub URL"]
    assert shown[0]["rows"][0] == "main"
    for text in ("GitHub", "Acme_Tools (acme_tools)", "https://github.com/acme/acme_tools",
                 "main", ">=15"):  # fmt: skip
        assert text in result.out, text
    assert afc.add_posts == [{
        "dt": "Release Group", "dn": BENCH, "method": "add_app",
        "args": {"app": {"name": "acme_tools", "title": "Acme_Tools",
                         "repository_url": "https://github.com/acme/acme_tools",
                         "branch": "main", "github_installation_id": "10001"}},
    }]  # fmt: skip
    assert writes(afc) == ["press.api.client.run_doc_method"]


def test_add_github_pasted_url(afc, cli, tty, search):
    _, answers = tty
    _, typed, _ = search
    answers["choose"] = ["From GitHub", "Paste"]
    answers["text"] = ["https://github.com/someone/tools.git", "ACME Prod"]
    typed += ["version"]
    result = cli("bench-add-app", BENCH)
    assert result.code == 0, result.err
    app_ = afc.add_posts[0]["args"]["app"]
    assert app_["repository_url"] == "https://github.com/someone/tools"
    assert app_["branch"] == "version-15"
    assert "github_installation_id" not in app_


def test_add_github_bad_url(afc, cli, tty):
    _, answers = tty
    answers["choose"] = ["From GitHub", "Paste"]
    answers["text"] = ["https://gitlab.com/someone/tools"]
    result = cli("bench-add-app", BENCH)
    assert result.code == 2
    assert "Not a GitHub repository URL" in result.err
    assert writes(afc) == []


def test_add_github_in_a_script(afc, cli):
    result = cli(
        "bench-add-app", BENCH, "--repo", "https://github.com/acme/tools", "--branch", "main",
        "--confirm", BENCH,
    )  # fmt: skip
    assert result.code == 0, result.err
    assert afc.add_posts[0]["args"]["app"]["name"] == "tools"


def test_add_github_unknown_branch(afc, cli):
    result = cli(
        "bench-add-app", BENCH, "--repo", "https://github.com/acme/tools", "--branch", "nope",
        "--confirm", BENCH,
    )  # fmt: skip
    assert result.code == 2
    assert "no branch nope" in result.err


def test_add_github_app_already_on_the_bench(afc, cli):
    result = cli(
        "bench-add-app", BENCH, "--repo", "https://github.com/frappe/erpnext", "--branch",
        "main", "--confirm", BENCH,
    )  # fmt: skip
    assert result.code == 2
    assert "already has app erpnext" in result.err
    assert writes(afc) == []


# --- 4.2 site-install-app -------------------------------------------------------------


def test_install_dry_run_preview(afc, cli):
    result = cli("site-install-app", SITE, "--app", "crm", "--dry-run")
    assert result.code == 0, result.err
    for text in ("Install preview", "work", "ACME Corp", "acme@example.com", "ACME Prod",
                 SITE, "Active", "Frappe CRM (crm, main)", "live site",
                 "Dry run: nothing was sent to FC."):  # fmt: skip
        assert text in result.out, text
    assert writes(afc) == []


def test_install_confirmed_success(afc, cli):
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE)
    assert result.code == 0, result.err
    assert afc.install_posts == [{"name": SITE, "app": "crm"}]
    assert writes(afc) == ["press.api.site.install_app"]
    assert "FC is installing the app - Install App on Site" in result.out
    assert "crm is installed on the site" in result.out


def test_install_failure_exits_8(afc, cli):
    afc.job_docs = [job("Failure", "Failure")]
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE)
    assert result.code == 8
    assert "Install App on Site" in result.err


def test_install_job_not_found_exits_6(afc, cli, monkeypatch):
    afc.install_makes_job = False
    monkeypatch.setattr(migrate_module, "FIND_LIMIT_SECONDS", 0)
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE)
    assert result.code == 6
    assert "not known" in result.err
    assert f"fcm site-show {SITE}" in result.err


def test_install_no_wait(afc, cli):
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE, "--no-wait")
    assert result.code == 0, result.err
    assert "The install started" in result.out
    assert "press.api.site.job" not in afc.calls


def test_install_json_events(afc, cli):
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE, "--json")
    assert result.code == 0, result.err
    events = [json.loads(line)["event"] for line in result.out.splitlines()]
    assert events[0] == "accepted" and events[-1] == "result"


def test_install_ctrl_c_during_watch(afc, cli, monkeypatch):
    def interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(apps_cli.time, "sleep", interrupt)
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE)
    assert result.code == 130
    assert "The install continues on FC" in result.out
    assert len(afc.install_posts) == 1


def test_install_unknown_answer_exits_6(afc, cli):
    afc.post_error = (502, {"message": "bad gateway"})
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE)
    assert result.code == 6
    assert f"fcm site-show {SITE}" in result.err


def test_install_app_with_plans_refused(afc, cli):
    result = cli("site-install-app", SITE, "--app", "helpdesk", "--confirm", SITE)
    assert result.code == 2
    assert "FC dashboard" in result.err
    assert writes(afc) == []


def test_install_app_not_on_bench(afc, cli):
    result = cli("site-install-app", SITE, "--app", "lms", "--confirm", SITE)
    assert result.code == 2
    assert f"fcm bench-add-app {BENCH}" in result.err


def test_install_inactive_site_refused(afc, cli):
    result = cli("site-install-app", "hr.acme.example.com", "--app", "crm", "--dry-run")
    assert result.code == 2
    assert "Inactive" in result.err


def test_install_job_in_progress_refused(afc, cli):
    afc.other_jobs = [{"name": "j-1", "job_type": "Backup Site", "status": "Running"}]
    result = cli("site-install-app", SITE, "--app", "crm", "--confirm", SITE)
    assert result.code == 2
    assert "Backup Site" in result.err
    assert writes(afc) == []


@pytest.mark.parametrize(
    "args",
    [
        ("site-install-app", SITE, "--app", "crm", "--json"),
        ("site-install-app", SITE, "--json"),
        ("site-install-app", "--app", "crm", "--json"),
    ],
)
def test_install_script_refusals(afc, cli, args):
    result = cli(*args)
    assert result.code == 2
    assert writes(afc) == []


def test_install_every_app_present(afc, cli, tty):
    afc.site_apps = []
    result = cli("site-install-app", SITE)
    assert result.code == 0, result.err
    assert "already has every app of its bench" in result.out


def test_install_app_step_marks_plans(afc, cli, tty):
    seen, answers = tty
    answers["choose"] = ["(crm"]
    answers["text"] = [SITE]
    result = cli("site-install-app", SITE)
    assert result.code == 0, result.err
    notes = seen["choose"][0]["notes"]
    assert notes["Helpdesk (helpdesk, main)"] == "has plans: install it from the FC dashboard"
    assert notes["Frappe CRM (crm, main)"] is None
    assert seen["text"] == [f"Type the site name to install the app ({SITE}):"]
    assert afc.install_posts == [{"name": SITE, "app": "crm"}]


def test_install_wrong_name_cancels(afc, cli, tty):
    _, answers = tty
    answers["choose"] = ["(crm"]
    answers["text"] = ["erp"]
    result = cli("site-install-app", SITE)
    assert result.code == 2
    assert writes(afc) == []


def test_install_walk_team_bench_site(afc, cli, tty):
    seen, answers = tty
    answers["choose"] = ["ACME Corp", BENCH, SITE, "(crm"]
    answers["text"] = ["nope"]
    result = cli("site-install-app")
    assert result.code == 2
    assert [c["prompt"] for c in seen["choose"]][:3] == ["Team", "Bench", "Site"]
    assert writes(afc) == []
