"""Group 5: team discovery, fan-out, resolvers and the inventory commands."""

import json

import pytest

from fc_manager.cli import picker
from fc_manager.inventory import (
    Ambiguous,
    Missing,
    Resolved,
    Team,
    parse_teams,
    resolve,
)

from .conftest import fixture, save_profile

# --- 5.1: team discovery --------------------------------------------------------------


def test_parse_teams_dict_form():
    teams = parse_teams(fixture("account_get.json")["message"]["teams"])
    assert len(teams) == 13
    assert teams[0] == Team("name-2", "team_title-1", owner="user@example.com")


def test_parse_teams_plain_string_form():
    teams = parse_teams(["team-own", "team-acme"])
    assert teams == [Team("team-own", "team-own"), Team("team-acme", "team-acme")]


def test_parse_teams_skips_junk_and_duplicates():
    teams = parse_teams([{"name": "a", "team_title": "A"}, {"name": "a"}, 42, {}])
    assert teams == [Team("a", "A")]


# --- 5.2: fan-out ---------------------------------------------------------------------


@pytest.fixture
def profile(env):
    save_profile("work")


def test_partial_failure_shows_other_teams(profile, fc, cli):
    fc.team_errors["team-beta"] = (403, fixture("error_permission.json"))
    result = cli("site", "list")
    assert result.code == 7
    assert "erp.acme.example.com" in result.out and "own.example.com" in result.out
    assert "erp.beta.example.com" not in result.out
    assert "Beta Ltd" in result.err and "1 of 3 teams failed" in result.err


def test_partial_failure_json(profile, fc, cli):
    fc.team_errors["team-beta"] = (403, fixture("error_permission.json"))
    result = cli("bench", "list", "--json")
    assert result.code == 7
    names = {b["name"] for b in json.loads(result.out)}
    assert names == {"bench-0001", "bench-1234", "bench-1240"}
    assert json.loads(result.err)["failures"][0]["kind"] == "permission"


def test_single_team_failure_is_that_error(profile, fc, cli):
    fc.team_errors["team-acme"] = (403, fixture("error_permission.json"))
    result = cli("bench", "list", "--team", "team-acme")
    assert result.code == 4


def test_child_team_duplicates_appear_once(profile, fc, cli):
    # bench.all and site.all include child teams: the parent sees the child's rows too.
    fc.benches["team-own"] = fc.benches["team-own"] + fc.benches["team-beta"]
    fc.sites["team-own"] = fc.sites["team-own"] + fc.sites["team-beta"]
    benches = json.loads(cli("bench", "list", "--json").out)
    assert [b["name"] for b in benches].count("bench-0981") == 1
    sites = json.loads(cli("site", "list", "--json").out)
    erp_beta = [s for s in sites if s["name"] == "erp.beta.example.com"]
    assert len(erp_beta) == 1
    assert erp_beta[0]["team"]["name"] == "team-beta"  # owner from the row's team field


# --- 5.3: resolvers -------------------------------------------------------------------

TEAMS = [Team("team-acme", "ACME Corp"), Team("team-beta", "Beta Ltd"), Team("t3", "Prod")]


def _resolve(query, items=TEAMS):
    return resolve(items, query, name=lambda t: t.name, title=lambda t: t.title)


def test_resolve_by_name():
    assert _resolve("team-beta") == Resolved(TEAMS[1])


def test_resolve_by_title_case_insensitive():
    assert _resolve("acme corp") == Resolved(TEAMS[0])


def test_name_wins_over_title():
    items = [Team("Prod", "Other"), Team("x", "Prod")]
    assert _resolve("Prod", items) == Resolved(items[0])


def test_two_titles_are_ambiguous():
    items = [Team("a", "Prod"), Team("b", "prod")]
    result = _resolve("Prod", items)
    assert isinstance(result, Ambiguous) and len(result.candidates) == 2


def test_no_match_gives_at_most_5_close_matches():
    items = [Team(f"bench-{i}", f"Prod {i}") for i in range(10)]
    result = _resolve("Prod", items)
    assert isinstance(result, Missing)
    assert 0 < len(result.close_matches) <= 5


# --- 5.4: team list -------------------------------------------------------------------


def test_team_list_table(profile, fc, cli):
    result = cli("team", "list")
    assert result.code == 0
    for text in ("team-own", "ACME Corp", "Beta Ltd", "3 teams"):
        assert text in result.out


def test_team_list_json(profile, fc, cli):
    rows = json.loads(cli("team", "list", "--json").out)
    assert rows[1] == {
        "name": "team-acme",
        "title": "ACME Corp",
        "owner": "acme@example.com",
        "label": "ACME Corp",
    }


# --- 5.5: bench list ------------------------------------------------------------------


def test_bench_list_all_teams_shows_team_column(profile, fc, cli):
    result = cli("bench", "list")
    assert result.code == 0
    for text in ("Team", "bench-1234", "ACME Prod", "bench-0981", "Beta Ltd", "4 benches in 3"):
        assert text in result.out


def test_bench_list_single_team(profile, fc, cli):
    rows = json.loads(cli("bench", "list", "--team", "team-acme", "--json").out)
    assert {b["name"] for b in rows} == {"bench-1234", "bench-1240"}
    assert set(rows[0]) >= {"team", "name", "title", "version", "status", "sites", "apps"}


def test_bench_list_team_by_title(profile, fc, cli):
    rows = json.loads(cli("bench", "list", "--team", "beta ltd", "--json").out)
    assert [b["name"] for b in rows] == ["bench-0981"]


def test_bench_list_unknown_team_lists_valid_teams(profile, fc, cli):
    result = cli("bench", "list", "--team", "nope")
    assert result.code == 2
    assert "team-acme" in result.err and "ACME Corp" in result.err


# --- 5.6: site list -------------------------------------------------------------------


def test_site_list_columns(profile, fc, cli):
    result = cli("site", "list", "--team", "team-acme")
    assert result.code == 0
    for text in ("Site", "Bench", "Status", "Version", "Region", "Update", "available"):
        assert text in result.out


def test_site_list_bench_filter_by_name(profile, fc, cli):
    rows = json.loads(cli("site", "list", "--bench", "bench-1234", "--json").out)
    assert {s["name"] for s in rows} == {"erp.acme.example.com", "hr.acme.example.com"}


def test_site_list_bench_filter_by_title(profile, fc, cli):
    rows = json.loads(cli("site", "list", "--bench", "acme prod", "--json").out)
    assert {s["bench"] for s in rows} == {"bench-1234"}


def test_site_list_ambiguous_bench_piped_exits_2_with_candidates(profile, fc, cli):
    result = cli("site", "list", "--bench", "Prod")
    assert result.code == 2
    assert "bench-1240" in result.err and "bench-0981" in result.err
    assert "ACME Corp" in result.err and "Beta Ltd" in result.err


def test_site_list_ambiguous_bench_on_terminal_uses_picker(profile, fc, cli, monkeypatch):
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    seen = {}

    def choose(prompt, options):
        seen["labels"] = [label for label, _ in options]
        return next(value for label, value in options if "bench-0981" in label)

    monkeypatch.setattr(picker, "choose", choose)
    result = cli("site", "list", "--bench", "Prod")
    assert result.code == 0
    assert len(seen["labels"]) == 2
    assert "erp.beta.example.com" in result.out
    assert "stage.acme.example.com" not in result.out


def test_site_list_unknown_bench_is_not_found(profile, fc, cli):
    result = cli("site", "list", "--bench", "zzz")
    assert result.code == 5


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            "active",
            {
                "own.example.com",
                "erp.acme.example.com",
                "stage.acme.example.com",
                "erp.beta.example.com",
            },
        ),
        ("inactive", {"hr.acme.example.com"}),
        ("update-available", {"erp.acme.example.com"}),
    ],
)
def test_site_list_status_filter(profile, fc, cli, status, expected):
    rows = json.loads(cli("site", "list", "--status", status, "--json").out)
    assert {s["name"] for s in rows} == expected


def test_site_list_empty_message(profile, fc, cli):
    result = cli("site", "list", "--team", "team-beta", "--status", "broken")
    assert result.code == 0
    assert "No sites found in team Beta Ltd" in result.out


# --- 5.7: site show -------------------------------------------------------------------


def test_site_show_found_with_apps(profile, fc, cli):
    result = cli("site", "show", "erp.acme.example.com")
    assert result.code == 0, result.err
    for text in ("ACME Corp", "bench-1234", "f1-mumbai.example.com", "erpnext", "version-16"):
        assert text in result.out


def test_site_show_finds_team_and_uses_it(profile, fc, cli):
    data = json.loads(cli("site", "show", "erp.beta.example.com", "--json").out)
    assert data["team"]["name"] == "team-beta"
    assert [a["name"] for a in data["apps"]] == ["frappe", "erpnext", "hrms"]


def test_site_show_picker_when_missing_on_terminal(profile, fc, cli, monkeypatch):
    monkeypatch.setattr(picker, "is_interactive", lambda json_mode: not json_mode)
    seen = {}

    def choose(prompt, options):
        seen["labels"] = [label for label, _ in options]
        return options[0][1]

    monkeypatch.setattr(picker, "choose", choose)
    result = cli("site", "show")
    assert result.code == 0
    assert len(seen["labels"]) == 5  # every site in every team
    assert any("ACME Corp / ACME Prod" in label for label in seen["labels"])


def test_site_show_missing_in_json_mode_exits_2(profile, fc, cli):
    assert cli("site", "show", "--json").code == 2


def test_site_show_not_found_exits_5(profile, fc, cli):
    result = cli("site", "show", "missing.example.com")
    assert result.code == 5
    assert "missing.example.com" in result.err


def test_bench_title_is_not_guessed_when_a_team_failed(profile, fc, cli):
    # Beta also has a bench titled "Prod". If Beta fails, "Prod" must not resolve to ACME's.
    fc.team_errors["team-beta"] = (403, fixture("error_permission.json"))
    result = cli("site", "list", "--bench", "Prod")
    assert result.code == 7
    assert "stage.acme.example.com" not in result.out
    assert "Beta Ltd" in result.err


def test_bench_exact_name_still_works_when_another_team_failed(profile, fc, cli):
    fc.team_errors["team-beta"] = (403, fixture("error_permission.json"))
    result = cli("site", "list", "--bench", "bench-1240", "--json")
    assert result.code == 0
    assert [s["name"] for s in json.loads(result.out)] == ["stage.acme.example.com"]


def test_counts_use_singular_for_one(profile, fc, cli):
    assert "1 site in bench" in cli("site", "list", "--bench", "bench-1240").out


# --- real FC shapes (fixtures recorded 2026-11-09) -------------------------------------


def test_parse_real_bench_row():
    from fc_manager.inventory import parse_bench

    team = Team("name-2", "team_title-1")
    bench = parse_bench(fixture("bench_all.json")["message"][0], team)
    assert (bench.name, bench.title, bench.version) == ("group-2", "title-3", "Version 16")
    assert (bench.status, bench.sites, bench.apps) == ("Active", 1, 10)


def test_parse_real_site_row():
    from fc_manager.inventory import parse_site

    team = Team("name-2", "team_title-1")
    site = parse_site(fixture("site_all.json")["message"][0], team)
    assert site.name == "name-15.example.com"
    assert (site.bench, site.bench_title) == ("group-1", "title-1")
    assert (site.status, site.version, site.region) == ("Active", "Version 16", "title-2")
    assert site.update_available is False


def test_real_site_rows_carry_their_team():
    rows = fixture("site_all.json")["message"]
    assert all(row["team"] for row in rows)


def test_real_bench_rows_have_no_team_field():
    # This is why bench rows take the team of the request (design D5).
    assert all("team" not in row for row in fixture("bench_all.json")["message"])


def test_parse_real_installed_apps():
    from fc_manager.inventory import parse_app

    apps = [parse_app(row) for row in fixture("site_installed_apps.json")["message"]]
    assert [a.name for a in apps] == ["frappe", "erpnext", "hrms"]
    assert apps[0].branch == "version-16"
    assert apps[0].repository == "https://github.com/frappe/frappe"
    assert len(apps[0].hash) == 12


def test_unknown_team_returns_no_rows():
    # FC answers 200 with no rows for an unknown X-Press-Team: no silent fallback.
    assert fixture("unknown_team_site_all.json") == {"message": []}


# --- 7.1: team labels -----------------------------------------------------------------


def test_labels_use_title_when_unique():
    from fc_manager.inventory import assign_labels

    teams = assign_labels([Team("a", "ACME", "x@a.com"), Team("b", "Beta", "y@b.com")])
    assert [t.display for t in teams] == ["ACME", "Beta"]


def test_labels_use_owner_when_title_is_shared():
    from fc_manager.inventory import assign_labels

    teams = assign_labels(
        [
            Team("a", "Parent Team", "x@a.com"),
            Team("b", "parent team", "y@b.com"),
            Team("c", "Parent Team", ""),
            Team("d", "Solo", "z@d.com"),
        ]
    )
    assert [t.display for t in teams] == ["x@a.com", "y@b.com", "c", "Solo"]


@pytest.fixture
def parent_teams(fc):
    for team in fc.teams:
        team["team_title"] = "Parent Team"
    return fc


def test_shared_titles_show_owner_in_lists(profile, parent_teams, cli):
    result = cli("bench", "list")
    assert result.code == 0
    assert "Parent Team" not in result.out
    assert "acme@example.com" in result.out and "beta@example.com" in result.out


def test_team_list_has_owner_column(profile, fc, cli):
    result = cli("team", "list")
    assert "Owner" in result.out and "acme@example.com" in result.out


def test_team_option_accepts_owner_email(profile, parent_teams, cli):
    rows = json.loads(cli("bench", "list", "--team", "BETA@example.com", "--json").out)
    assert [b["name"] for b in rows] == ["bench-0981"]


def test_ambiguous_bench_candidates_show_owner(profile, parent_teams, cli):
    result = cli("site", "list", "--bench", "Prod")
    assert result.code == 2
    assert "acme@example.com" in result.err and "beta@example.com" in result.err


# --- 7.2: worker limit ----------------------------------------------------------------


def test_fanout_uses_at_most_8_workers(monkeypatch):
    import fc_manager.inventory as inv

    seen = {}

    class Pool(inv.ThreadPoolExecutor):
        def __init__(self, max_workers):
            seen["workers"] = max_workers
            super().__init__(max_workers=max_workers)

    monkeypatch.setattr(inv, "ThreadPoolExecutor", Pool)
    teams = [Team(f"t{i}", f"T{i}") for i in range(13)]
    service = inv.Inventory(client=None)
    service._fanout(teams, lambda team: [])
    assert inv.MAX_WORKERS == 8
    assert seen["workers"] == 8


# --- 7.3 / 7.4: denied site detail and owner hints ------------------------------------


@pytest.fixture
def denied_fc(env):
    import respx

    from .conftest import BASE, default_fake

    fake = default_fake()
    original = fake.handle

    def handle(request):
        method = request.url.path.rsplit("/", 1)[-1]
        if method in ("press.api.site.get", "press.api.site.installed_apps"):
            import httpx

            return httpx.Response(403, json=fixture("error_not_found.json"))
        return original(request)

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.route().mock(side_effect=handle)
        yield fake


def test_site_show_denied_detail_shows_known_fields(env, denied_fc, cli):
    save_profile("work")
    result = cli("site", "show", "erp.acme.example.com")
    assert result.code == 4
    for text in ("ACME Corp", "bench-1234", "Active", "Version 15", "Mumbai", "available"):
        assert text in result.out
    assert "not permitted for your role" in result.out
    assert "acme@example.com" in result.err  # hint names the team owner
    assert "--team" not in result.err


def test_site_show_denied_detail_json(env, denied_fc, cli):
    save_profile("work")
    result = cli("site", "show", "erp.acme.example.com", "--json")
    assert result.code == 4
    data = json.loads(result.out)
    assert data["detail"] == "not_permitted" and data["apps"] is None
    assert data["status"] == "Active"
    assert json.loads(result.err)["kind"] == "permission"


def test_single_team_permission_error_hint_names_owner(profile, fc, cli):
    fc.team_errors["team-acme"] = (403, fixture("error_permission.json"))
    result = cli("bench", "list", "--team", "team-acme")
    assert result.code == 4
    assert "Ask acme@example.com for access" in result.err
