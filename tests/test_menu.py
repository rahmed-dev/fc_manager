"""cli-hub group 3, site-migrate group 6, site-update group 6 and add-app group 5: `fcm`
with no command opens the menu (team, bench, action, and the site step for a site
action)."""

# ruff: noqa: F811 - the dfc and tty fixtures come from test_cli_deploy

import pytest

from fc_manager.cli import deploy as deploy_cli
from fc_manager.cli import menu as menu_cli
from fc_manager.cli import migrate as migrate_cli
from fc_manager.cli import picker
from fc_manager.cli import update as update_cli
from fc_manager.errors import PermissionDenied

from .test_cli_deploy import dfc, tty  # noqa: F401 - shared fixtures

BACK = picker.GoBack
CTRL_C = picker.Cancelled


@pytest.fixture
def menu(monkeypatch):
    """Scripted picker.choose for the menu. Each answer is a team or bench FC name, an
    action value, BACK (Esc), or CTRL_C. Records (prompt, labels, path) for each prompt."""
    script: list = []
    prompts: list = []

    def choose(prompt, options, *, back=False, path=None, space_picks=False, disabled=None):
        prompts.append((prompt, [label for label, _ in options], path))
        answer = script.pop(0)
        if answer is BACK:
            raise picker.GoBack
        if answer is CTRL_C:
            raise picker.Cancelled("Cancelled, nothing done")
        for _, value in options:
            if answer in (getattr(value, "name", value), getattr(value, "app", None)):
                return value
        raise AssertionError(f"{answer!r} not offered at {prompt!r}")

    monkeypatch.setattr(picker, "choose", choose)
    return script, prompts


def names(prompts):
    return [prompt for prompt, _, _ in prompts]


def test_fcm_without_terminal_prints_help(env, cli):
    result = cli()
    assert result.code == 0
    assert "Usage" in result.out and "bench-deploy" in result.out


def test_team_then_bench_of_that_team_then_show(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", "show", "quit"]
    result = cli()
    assert result.code == 0, result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    assert prompts[0][2] == "work"
    assert prompts[1][1] == ["ACME Prod (bench-1234)", "Prod (bench-1240)"]  # team-acme only
    assert prompts[2][2] == "work > ACME Corp > ACME Prod (bench-1234)"
    assert "Bench ACME Prod" in result.out  # the bench-show output
    bench_calls = [team for method, team, _ in dfc.teams_seen if method.endswith("bench.all")]
    assert bench_calls == ["team-acme"]


def test_action_menu_names_the_direct_commands(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", "quit"]
    cli()
    assert prompts[2][1] == [
        "Show bench (bench-show)",
        "Deploy app updates (bench-deploy)",
        "Add an app (bench-add-app)",
        "Migrate a site (site-migrate)",
        "Update a site (site-update)",
        "Install an app (site-install-app)",
        "Pick another bench",
        "Quit",
    ]


def test_wrong_title_sends_nothing_and_returns_to_actions(dfc, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "deploy", "quit"]
    answers["many"] = ["all", []]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    assert dfc.posts == []
    assert "ancelled" in result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    # 3.5: GET only, and after the bench pick only the picked team.
    assert {verb for _, _, verb in dfc.teams_seen} == {"GET"}
    assert {team for _, team, _ in after_bench_pick_calls(dfc)} == {"team-acme"}


def after_bench_pick_calls(fc):
    first = next(i for i, c in enumerate(fc.teams_seen) if c[0].endswith("deploy_information"))
    return fc.teams_seen[first:]


def test_action_error_is_printed_and_menu_stays(dfc, cli, tty, menu, monkeypatch):
    def denied(s, bench):
        raise PermissionDenied("Not permitted", target="team ACME", hint="Ask the owner.")

    monkeypatch.setattr(deploy_cli, "show_bench", denied)
    script, prompts = menu
    script += ["team-acme", "bench-1234", "show", "quit"]
    result = cli()
    assert result.code == 0
    assert "Not permitted" in result.err and "Ask the owner." in result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]


def test_esc_walks_back_one_step_and_out(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", BACK, BACK, BACK]
    result = cli()
    assert result.code == 0
    assert names(prompts) == ["Team", "Bench", "Action", "Bench", "Team"]
    assert dfc.posts == []


def test_esc_at_deploy_app_step_returns_to_actions(dfc, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "deploy", "quit"]
    answers["many"] = [picker.GoBack]
    result = cli()
    assert result.code == 0, result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    assert dfc.posts == []


def test_ctrl_c_at_menu_prompt_exits_130(dfc, cli, tty, menu):
    script, _ = menu
    script += ["team-acme", CTRL_C]
    result = cli()
    assert result.code == 130
    assert dfc.posts == []


def test_other_bench_entry_goes_to_bench_step(dfc, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", "bench", "bench-1240", "quit"]
    result = cli()
    assert result.code == 0
    assert names(prompts) == ["Team", "Bench", "Action", "Bench", "Action"]
    assert prompts[4][2] == "work > ACME Corp > Prod (bench-1240)"


# --- site-migrate group 6: registry and site step ------------------------------------

SITE = "erp.acme.example.com"
SITE_PATH = f"work > ACME Corp > ACME Prod (bench-1234) > {SITE}"


@pytest.fixture
def mig(dfc, monkeypatch):
    """The deploy fake FC, with the migrate job docs and no real sleeping."""
    monkeypatch.setattr(migrate_cli.time, "sleep", lambda _s: None)
    return dfc


def migrate_posts(fc):
    return [m for m, _, verb in fc.teams_seen if verb == "POST"]


def test_every_entry_names_its_direct_command():
    for action in menu_cli.ACTIONS:
        assert action.title == f"{action.label} ({action.command})"
        assert action.scope in ("bench", "site")


def test_site_step_lists_sites_of_the_bench_only(mig, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "migrate", SITE, "quit"]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Site", "Action"]
    assert prompts[3][1] == [f"{SITE}  (Active)", "hr.acme.example.com  (Inactive)"]
    assert prompts[3][2] == "work > ACME Corp > ACME Prod (bench-1234)"
    # After the action, the action menu of the same bench, with no site in the path.
    assert prompts[4][2] == "work > ACME Corp > ACME Prod (bench-1234)"


def test_migrate_from_menu_sends_nothing_before_the_typed_name(mig, cli, tty, menu):
    script, _ = menu
    seen, answers = tty
    script += ["team-acme", "bench-1234", "migrate", SITE, "quit"]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    assert "Migrate preview" in result.out
    assert seen["text"] == [f"Type the site name to migrate ({SITE}):"]
    assert migrate_posts(mig) == []
    assert "ancelled" in result.err


def test_migrate_from_menu_with_typed_name(mig, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "migrate", SITE, "quit"]
    answers["text"] = [SITE]
    result = cli()
    assert result.code == 0, result.err
    assert migrate_posts(mig) == ["press.api.site.migrate"]
    assert "the site is migrated" in result.out
    assert names(prompts)[-1] == "Action"


def test_site_path_reaches_the_action(mig, cli, tty, menu, monkeypatch):
    got = []
    monkeypatch.setattr(
        migrate_cli, "migrate_site", lambda s, site, opts, *, in_menu, path: got.append(path)
    )
    script, _ = menu
    script += ["team-acme", "bench-1234", "migrate", SITE, "quit"]
    assert cli().code == 0
    assert got == [SITE_PATH]


def test_esc_at_site_step_returns_to_actions(mig, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1234", "migrate", BACK, "quit"]
    result = cli()
    assert result.code == 0, result.err
    assert names(prompts) == ["Team", "Bench", "Action", "Site", "Action"]
    assert migrate_posts(mig) == []


def test_bench_with_no_site(mig, cli, tty, menu):
    mig.sites["team-acme"] = [x for x in mig.sites["team-acme"] if x["group"] != "bench-1240"]
    script, prompts = menu
    script += ["team-acme", "bench-1240", "migrate", "quit"]
    result = cli()
    assert result.code == 0, result.err
    assert "Bench Prod has no site." in result.out
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]


def test_ctrl_c_in_migrate_watch_returns_to_actions(mig, cli, tty, menu, monkeypatch):
    def interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(migrate_cli.time, "sleep", interrupt)
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "migrate", SITE, "quit"]
    answers["text"] = [SITE]
    mig.job_docs = [{"name": "job-new", "status": "Running", "steps": []}]
    result = cli()
    assert result.code == 0, result.err
    assert "The migrate continues on FC" in result.out
    assert names(prompts) == ["Team", "Bench", "Action", "Site", "Action"]
    assert migrate_posts(mig) == ["press.api.site.migrate"]


# --- site-update group 6: the update entry and its site filter -------------------------


@pytest.fixture
def upd(dfc, monkeypatch):
    """The deploy fake FC, with no real sleeping in the update watch."""
    monkeypatch.setattr(update_cli.time, "sleep", lambda _s: None)
    return dfc


def test_update_entry_follows_migrate():
    names_ = [a.name for a in menu_cli.ACTIONS]
    assert names_.index("update") == names_.index("migrate") + 1
    update = next(a for a in menu_cli.ACTIONS if a.name == "update")
    assert update.scope == "site"
    assert update.site_filter is not None


def test_update_only_site_with_an_update_is_picked_with_no_list(upd, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "update", "quit"]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    # only erp.acme has an update (hr.acme has none): picked with no site list
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    assert f"Site: {SITE}  (Active)" in result.out
    assert "Update preview" in result.out


def test_update_bench_with_no_update_returns_to_actions(upd, cli, tty, menu):
    script, prompts = menu
    script += ["team-acme", "bench-1240", "update", "quit"]
    result = cli()
    assert result.code == 0, result.err
    assert "No site of bench Prod has an update." in result.out
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    assert migrate_posts(upd) == []


def test_update_from_menu_sends_nothing_before_the_typed_name(upd, cli, tty, menu):
    script, _ = menu
    seen, answers = tty
    script += ["team-acme", "bench-1234", "update", "quit"]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    assert "Update preview" in result.out
    assert seen["text"] == [f"Type the site name to update ({SITE}):"]
    assert migrate_posts(upd) == []
    assert "ancelled" in result.err


def test_update_from_menu_with_typed_name(upd, cli, tty, menu):
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "update", "quit"]
    answers["text"] = [SITE]
    result = cli()
    assert result.code == 0, result.err
    assert migrate_posts(upd) == ["press.api.site.update"]
    assert "the site is updated" in result.out
    assert names(prompts)[-1] == "Action"


def test_ctrl_c_in_update_watch_returns_to_actions(upd, cli, tty, menu, monkeypatch):
    def interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(update_cli.time, "sleep", interrupt)
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "update", "quit"]
    answers["text"] = [SITE]
    upd.update_records = [{"name": "su-new", "status": "Running", "steps": []}]
    result = cli()
    assert result.code == 0, result.err
    assert "The update continues on FC" in result.out
    assert names(prompts) == ["Team", "Bench", "Action", "Action"]
    assert migrate_posts(upd) == ["press.api.site.update"]


# --- add-app group 5: "Add an app", "Deploy now?" and "Install an app" ------------------


@pytest.fixture
def app_menu(dfc, monkeypatch):
    """The deploy fake FC, scripted yes/no answers, a scripted search (each search picks
    the first row for "crm"), and no real sleeping. `asked` records the yes/no prompts;
    "Add another app?" is always no, "Deploy now?" is answer["deploy"]."""
    from fc_manager.cli import apps as apps_cli

    monkeypatch.setattr(apps_cli.time, "sleep", lambda _s: None)
    asked = []
    answer = {"deploy": False}

    def ask_yes_no(prompt, *, default=False):
        asked.append((prompt, default))
        return answer["deploy"] if prompt == "Deploy now?" else False

    def search(prompt, find, *, back=False, path=None):
        return find("crm")[0][1]

    monkeypatch.setattr(picker, "ask_yes_no", ask_yes_no)
    monkeypatch.setattr(picker, "search", search)
    return dfc, asked, answer


def test_app_entries_order():
    names_ = [a.name for a in menu_cli.ACTIONS]
    assert names_.index("add-app") == names_.index("deploy") + 1
    assert names_.index("install-app") == names_.index("update") + 1
    scopes = {a.name: a.scope for a in menu_cli.ACTIONS}
    assert scopes["add-app"] == "bench" and scopes["install-app"] == "site"


def test_add_from_menu_sends_nothing_before_the_typed_title(app_menu, cli, tty, menu):
    fc, asked, _ = app_menu
    script, prompts = menu
    seen, answers = tty
    script += ["team-acme", "bench-1234", "add-app", "market", "quit"]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    assert "Add-app preview" in result.out
    assert seen["text"] == ["Type the bench title to add the app (ACME Prod):"]
    assert migrate_posts(fc) == []
    assert asked == [("Add another app?", False)]  # no "Deploy now?" after a cancelled add
    assert names(prompts) == ["Team", "Bench", "Action", "Add an app from", "Action"]


def test_add_then_no_deploy_returns_to_actions(app_menu, cli, tty, menu):
    fc, asked, _ = app_menu
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "add-app", "market", "quit"]
    answers["text"] = ["ACME Prod"]
    result = cli()
    assert result.code == 0, result.err
    assert migrate_posts(fc) == ["press.api.bench.add_apps"]
    assert asked == [("Add another app?", False), ("Deploy now?", False)]
    assert names(prompts)[-1] == "Action"
    assert "Deploy preview" not in result.out


def test_add_then_deploy_starts_the_deploy_walk(app_menu, cli, tty, menu):
    fc, asked, answer = app_menu
    answer["deploy"] = True
    script, prompts = menu
    seen, answers = tty
    script += ["team-acme", "bench-1234", "add-app", "market", "quit"]
    answers["text"] = ["ACME Prod", "nope"]  # add confirmed; deploy title wrong
    answers["many"] = ["all", []]
    result = cli()
    assert result.code == 0, result.err
    assert asked == [("Add another app?", False), ("Deploy now?", False)]
    assert seen["many"][0]["prompt"] == "App updates to deploy"
    assert "Deploy preview" in result.out
    assert seen["text"][1].startswith("Type the bench title to deploy")
    assert migrate_posts(fc) == ["press.api.bench.add_apps"]  # no deploy POST


def test_esc_at_source_choice_returns_to_actions(app_menu, cli, tty, menu):
    fc, _, _ = app_menu
    script, prompts = menu
    script += ["team-acme", "bench-1234", "add-app", BACK, "quit"]
    result = cli()
    assert result.code == 0, result.err
    assert names(prompts)[-1] == "Action"
    assert migrate_posts(fc) == []


def test_install_from_menu_sends_nothing_before_the_typed_name(app_menu, cli, tty, menu):
    fc, _, _ = app_menu
    script, prompts = menu
    seen, answers = tty
    script += ["team-acme", "bench-1234", "install-app", SITE, "crm", "quit"]
    answers["text"] = ["nope"]
    result = cli()
    assert result.code == 0, result.err
    assert "Install preview" in result.out
    assert seen["text"] == [f"Type the site name to install the app ({SITE}):"]
    assert migrate_posts(fc) == []
    assert names(prompts) == ["Team", "Bench", "Action", "Site", f"App to install on {SITE}",
                              "Action"]  # fmt: skip


def test_ctrl_c_in_install_watch_returns_to_actions(app_menu, cli, tty, menu, monkeypatch):
    from fc_manager.cli import apps as apps_cli

    def interrupt(_s):
        raise KeyboardInterrupt

    fc, _, _ = app_menu
    monkeypatch.setattr(apps_cli.time, "sleep", interrupt)
    fc.job_docs = [{"name": "job-new", "status": "Running", "steps": []}]
    script, prompts = menu
    _, answers = tty
    script += ["team-acme", "bench-1234", "install-app", SITE, "crm", "quit"]
    answers["text"] = [SITE]
    result = cli()
    assert result.code == 0, result.err
    assert "The install continues on FC" in result.out
    assert names(prompts)[-1] == "Action"
    assert migrate_posts(fc) == ["press.api.site.install_app"]
