"""App service tests (add-app group 3), on the fixture shapes."""

import copy
import json
import time

import pytest
import respx

from fc_manager import migrate as migrate_module
from fc_manager.api.client import FCClient
from fc_manager.apps import (
    AddPlan,
    AppService,
    AppSource,
    GitHubApp,
    GitHubPlan,
    GitHubRepo,
    InstallPlan,
    MarketApp,
    SiteApp,
    order_branches,
    parse_all_apps,
    parse_available_apps,
    parse_github_repos,
    parse_repo_url,
)
from fc_manager.errors import InstallFailed, InstallUnknown, UsageError
from fc_manager.inventory import Bench, Site, Team
from fc_manager.redact import Credentials
from fc_manager.search import SearchIndex

from .conftest import fixture, method_url

TEAM = Team(name="team-acme", title="ACME", owner="owner@acme.example.com")
BENCH = Bench(TEAM, "bench-1234", "ACME Prod", "Version 16", "Active", 2, 3)
SITE = Site(TEAM, "erp.acme.example.com", "bench-1234", "ACME Prod", "Active", "16", "", False)
SRC = AppSource("src-0001", "main", "frappe/crm")
CRM = MarketApp("crm", "Frappe CRM", (SRC,))
CRM_SITE = SiteApp("crm", "Frappe CRM", "main", "src-0001", "frappe/crm", False)


def service() -> AppService:
    return AppService(FCClient(Credentials("k-1234567", "s-1234567"), sleep=lambda _s: None))


def running_row(name, job_type="Install App on Site", status="Pending") -> dict:
    return {"id": name, "name": job_type, "status": status, "steps": []}


def install_job(status="Running", step_status="Running", name="job-7") -> dict:
    data = copy.deepcopy(fixture("site_job_install.json")["message"])
    data["name"] = name
    data["status"] = status
    data["steps"][0]["status"] = step_status
    return data


# --- 3.2 parsers ----------------------------------------------------------------------


def test_parse_all_apps_fixture_shape():
    apps = parse_all_apps(fixture("bench_all_apps.json")["message"])
    assert len(apps) == 20
    compatible = [a for a in apps if a.compatible]
    assert len(compatible) == 19
    first = compatible[0]
    assert first.sources[0].branch
    assert first.sources[0].repository.count("/") == 1
    assert not [a for a in apps if not a.compatible][0].sources


def test_parse_all_apps_missing_fields():
    apps = parse_all_apps(
        [{"app": "x", "sources": [{"branch": "main"}, {"name": "s"}]}, {"title": "no app"}, None]
    )
    assert [(a.app, a.title, len(a.sources)) for a in apps] == [("x", "x", 1)]
    assert apps[0].sources[0] == AppSource("s", "", "")
    assert parse_all_apps(None) == []


def test_parse_available_apps_fixture_shape():
    apps = parse_available_apps(fixture("site_available_apps.json")["message"])
    assert [a.branch for a in apps] == ["main", "version-16"]
    assert apps[0].title == "app_title-1"  # title is null: app_title is the fallback
    assert apps[1].title == "title-25"
    assert apps[0].repository == "repository_url-1.example.com"
    assert all(a.pickable for a in apps)


def test_parse_available_apps_title_fallback_and_plans():
    apps = parse_available_apps(
        [
            {"app": "helpdesk", "has_plans_available": True, "plans": [{"name": "p"}]},
            {"app": "crm", "repository_url": "https://github.com/frappe/crm.git"},
            {"name": "no app"},
        ]
    )
    assert [(a.app, a.title, a.pickable) for a in apps] == [
        ("helpdesk", "helpdesk", False),
        ("crm", "crm", True),
    ]
    assert apps[1].repository == "frappe/crm"


# --- 3.3 bench group ------------------------------------------------------------------


def test_offered_apps_reads_all_apps_and_puts_compatible_first():
    rows = [
        {"app": "zeta", "title": "Zeta", "sources": [{"name": "s1", "branch": "main"}]},
        {"app": "old", "title": "Alpha", "sources": []},
        {"app": "crm", "title": "CRM", "sources": [{"name": "s2", "branch": "main"}]},
    ]
    with respx.mock() as router:
        route = router.get(method_url("press.api.bench.all_apps")).respond(json={"message": rows})
        apps = service().offered_apps(BENCH)
    assert [a.app for a in apps] == ["crm", "zeta", "old"]
    request = route.calls.last.request
    assert request.headers["X-Press-Team"] == "team-acme"
    assert request.url.params["name"] == "bench-1234"


def test_pick_app_unknown_and_not_compatible():
    old = MarketApp("old", "Old", ())
    with pytest.raises(UsageError) as info:
        AppService.pick_app(BENCH, [CRM, old], "missing")
    assert "missing" in info.value.message and info.value.exit_code == 2
    with pytest.raises(UsageError) as info:
        AppService.pick_app(BENCH, [CRM, old], "old")
    assert "old" in info.value.message and "Version 16" in info.value.message
    assert AppService.pick_app(BENCH, [CRM, old], "crm") is CRM


def test_pick_source():
    two = MarketApp("crm", "CRM", (SRC, AppSource("src-0002", "develop", "frappe/crm")))
    assert AppService.pick_source(BENCH, CRM, None) is SRC
    assert AppService.pick_source(BENCH, two, None) is None
    assert AppService.pick_source(BENCH, two, "src-0002").branch == "develop"
    with pytest.raises(UsageError) as info:
        AppService.pick_source(BENCH, two, "nope")
    assert info.value.exit_code == 2
    assert "main" in info.value.hint and "develop" in info.value.hint


def test_add_market_sends_one_post_with_every_app():
    lms_src = AppSource("src-0002", "main", "frappe/lms")
    lms = MarketApp("lms", "LMS", (lms_src,))
    with respx.mock() as router:
        route = router.post(method_url("press.api.bench.add_apps")).respond(json={})
        service().add_market(AddPlan(BENCH, ((CRM, SRC), (lms, lms_src))))
    assert route.call_count == 1
    assert route.calls.last.request.headers["X-Press-Team"] == "team-acme"
    assert json.loads(route.calls.last.request.content) == {
        "name": "bench-1234",
        "apps": [{"app": "crm", "source": "src-0001"}, {"app": "lms", "source": "src-0002"}],
    }


# --- 9.3 cache and search ---------------------------------------------------------------


def test_offered_apps_is_read_once_per_bench():
    svc = service()
    with respx.mock() as router:
        route = router.get(method_url("press.api.bench.all_apps")).respond(
            json=fixture("bench_all_apps.json")
        )
        svc.offered_apps(BENCH)
        svc.offered_apps(BENCH)
        index = svc.search_index(BENCH)
    assert route.call_count == 1
    assert len(index) == 19  # the not compatible app is left out


def _index(*apps):
    return SearchIndex(list(apps), key=lambda a: a[0], title=lambda a: a[1])


def test_search_rank_order():
    index = _index(
        ("whitelabel_helper", "Whitelabel Helper"),  # word prefix
        ("helpdesk", "Helpdesk"),  # name prefix
        ("help", "Help"),  # exact
        ("crm_shelp", "CRM"),  # inside the name
        ("zz_other", "Other"),  # no match
    )
    assert [a[0] for a in index.search("help")] == [
        "help", "helpdesk", "whitelabel_helper", "crm_shelp",
    ]  # fmt: skip


def test_search_letters_in_order_and_title():
    index = _index(("helpdesk", "Helpdesk"), ("crm", "Frappe CRM"), ("lms", "Learning"))
    assert index.search("hlpdsk")[0][0] == "helpdesk"
    assert index.search("frappe")[0][0] == "crm"  # word of the title
    assert index.search("earn")[0][0] == "lms"  # inside the title
    assert index.search("zzz") == []
    assert index.search("   ") == []


def test_search_limit_is_10():
    index = _index(*[(f"app_{n:03}", f"App {n}") for n in range(300)])
    rows = index.search("app")
    assert len(rows) == 10
    assert len(index.search("app", limit=3)) == 3


def test_search_speed_on_a_marketplace_size_list():
    rows = fixture("bench_all_apps.json")["message"] * 20  # 400 rows, the real size
    apps = [a for a in parse_all_apps(rows) if a.compatible]
    index = SearchIndex(apps, key=lambda a: a.app, title=lambda a: a.title)
    queries = ["h", "he", "hel", "help", "hlpdsk", "name", "title-9", "zz"] * 25
    started = time.perf_counter()
    for q in queries:
        index.search(q)
    per_query = (time.perf_counter() - started) / len(queries)
    assert per_query < 0.005, f"{per_query * 1000:.2f} ms per query"


# --- 9.4 GitHub -------------------------------------------------------------------------


def test_parse_github_repos_fixture():
    repos = parse_github_repos(fixture("github_options.json")["message"])
    assert [(r.full_name, r.installation, r.default_branch) for r in repos] == [
        ("acme/acme_theme", "10001", "develop"),
        ("acme/acme_tools", "10001", "main"),
    ]
    assert parse_github_repos(None) == []


@pytest.mark.parametrize(
    ("url", "full"),
    [
        ("https://github.com/acme/tools", "acme/tools"),
        ("https://github.com/acme/tools.git", "acme/tools"),
        ("https://github.com/acme/my.app/", "acme/my.app"),
    ],
)
def test_parse_repo_url(url, full):
    repo = parse_repo_url(url)
    assert repo.full_name == full
    assert repo.installation is None


@pytest.mark.parametrize(
    "url", ["https://gitlab.com/acme/tools", "github.com/acme/tools", "https://github.com/acme"]
)
def test_parse_repo_url_refuses(url):
    with pytest.raises(UsageError) as info:
        parse_repo_url(url)
    assert info.value.exit_code == 2


def test_order_branches():
    names = [b["name"] for b in fixture("github_branches.json")["message"]]
    assert order_branches(names, "main") == ["main", "version-15", "develop", "feature-x"]


def test_github_branches_and_app_send_the_installation():
    repo = GitHubRepo("acme", "acme_tools", "10001", "main")
    with respx.mock() as router:
        branches = router.get(method_url("press.api.github.branches")).respond(
            json=fixture("github_branches.json")
        )
        app_route = router.get(method_url("press.api.github.app")).respond(
            json={"message": {"name": "acme_tools", "title": "Acme Tools",
                              "frappe_version": ">=15"}}
        )  # fmt: skip
        router.get(method_url("press.api.bench.deploy_information")).respond(
            json=fixture("bench_deploy_information.json")
        )
        svc = service()
        assert svc.github_branches(BENCH, repo)[0] == "main"
        app = svc.github_app(BENCH, repo, "main")
    assert app == GitHubApp("acme_tools", "Acme Tools", ">=15")
    assert branches.calls.last.request.url.params["installation"] == "10001"
    params = app_route.calls.last.request.url.params
    assert (params["owner"], params["repository"], params["branch"]) == (
        "acme", "acme_tools", "main",
    )  # fmt: skip


def test_github_app_already_on_the_bench():
    repo = parse_repo_url("https://github.com/frappe/erpnext")
    with respx.mock() as router:
        app_route = router.get(method_url("press.api.github.app")).respond(
            json={"message": {"name": "erpnext", "title": "ERPNext"}}
        )
        router.get(method_url("press.api.bench.deploy_information")).respond(
            json=fixture("bench_deploy_information.json")
        )
        with pytest.raises(UsageError) as info:
            service().github_app(BENCH, repo, "version-15")
    assert "already has app erpnext" in info.value.message
    assert "installation" not in app_route.calls.last.request.url.params


def test_add_github_sends_run_doc_method():
    repo = GitHubRepo("acme", "acme_tools", "10001")
    plan = GitHubPlan(BENCH, repo, "main", GitHubApp("acme_tools", "Acme Tools", ">=15"))
    with respx.mock() as router:
        route = router.post(method_url("press.api.client.run_doc_method")).respond(json={})
        service().add_github(plan)
    assert route.call_count == 1
    assert json.loads(route.calls.last.request.content) == {
        "dt": "Release Group",
        "dn": "bench-1234",
        "method": "add_app",
        "args": {"app": {"name": "acme_tools", "title": "Acme Tools",
                         "repository_url": "https://github.com/acme/acme_tools",
                         "branch": "main", "github_installation_id": "10001"}},
    }  # fmt: skip


# --- 3.4 site -------------------------------------------------------------------------


def mock_reads(router, status="Active", running=()):
    router.get(method_url("press.api.site.get")).respond(json={"message": {"status": status}})
    return router.get(method_url("press.api.site.running_jobs")).respond(
        json={"message": list(running)}
    )


def test_check_site_passes_for_active():
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router)
        check = service().check_site(SITE)
    assert check.status == "Active"


@pytest.mark.parametrize("status", ["Inactive", "Broken", "Pending", ""])
def test_check_site_refuses_other_status(status):
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, status=status)
        with pytest.raises(UsageError) as info:
            service().check_site(SITE)
    assert (status or "unknown") in info.value.message
    assert info.value.exit_code == 2


def test_check_site_refuses_a_job_in_progress():
    with respx.mock(assert_all_called=False) as router:
        mock_reads(router, running=[running_row("j-9", "Backup Site", "Running")])
        with pytest.raises(UsageError) as info:
            service().check_site(SITE)
    assert "Backup Site" in info.value.message
    assert info.value.exit_code == 2


def test_offered_site_apps_puts_plans_last():
    rows = [
        {"app": "helpdesk", "title": "Helpdesk", "has_plans_available": True},
        {"app": "crm", "title": "CRM"},
    ]
    with respx.mock() as router:
        route = router.get(method_url("press.api.site.available_apps")).respond(
            json={"message": rows}
        )
        apps = service().offered_site_apps(SITE)
    assert [a.app for a in apps] == ["crm", "helpdesk"]
    assert route.calls.last.request.url.params["name"] == "erp.acme.example.com"


def test_pick_site_app():
    plans = SiteApp("helpdesk", "Helpdesk", "main", "s", "frappe/helpdesk", True)
    with pytest.raises(UsageError) as info:
        AppService.pick_site_app(SITE, [CRM_SITE, plans], "helpdesk")
    assert "FC dashboard" in info.value.hint and info.value.exit_code == 2
    with pytest.raises(UsageError) as info:
        AppService.pick_site_app(SITE, [CRM_SITE], "lms")
    assert "lms" in info.value.message
    assert "fcm bench-add-app bench-1234" in info.value.hint
    assert AppService.pick_site_app(SITE, [CRM_SITE], "crm") is CRM_SITE


def test_install_sends_one_post_with_no_plan():
    with respx.mock() as router:
        route = router.post(method_url("press.api.site.install_app")).respond(json={})
        service().install(InstallPlan(SITE, "Active", CRM_SITE))
    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "erp.acme.example.com", "app": "crm"}


def run_watch(router, running_seq, job_seq, final_status="Active"):
    running_iter = iter(running_seq)
    job_iter = iter(job_seq)
    router.get(method_url("press.api.site.running_jobs")).mock(
        side_effect=lambda r: respx.MockResponse(json={"message": next(running_iter)})
    )
    router.get(method_url("press.api.site.job")).mock(
        side_effect=lambda r: respx.MockResponse(json={"message": next(job_iter)})
    )
    router.get(method_url("press.api.site.get")).respond(json={"message": {"status": final_status}})
    plan = InstallPlan(SITE, "Active", CRM_SITE)
    return list(service().watch_install(plan, sleep=lambda _s: None))


def test_watch_install_finds_the_job_and_ends_on_success():
    with respx.mock(assert_all_called=False) as router:
        states = run_watch(
            router,
            running_seq=[[running_row("j-1", "Backup Site", "Running")], [running_row("job-7")]],
            job_seq=[install_job(), install_job("Success", "Success")],
        )
    assert [s.stage for s in states] == ["finding", "running", "success"]
    assert states[-1].job == "job-7"


def test_watch_install_failure_names_the_step():
    with respx.mock(assert_all_called=False) as router, pytest.raises(InstallFailed) as info:
        run_watch(
            router,
            running_seq=[[running_row("job-7", status="Running")]],
            job_seq=[install_job("Failure", "Failure")],
            final_status="Broken",
        )
    assert info.value.step == "Install App on Site"
    assert info.value.exit_code == 8
    assert "install" in info.value.message
    assert "Broken" in info.value.hint


def test_watch_install_job_not_found(monkeypatch):
    monkeypatch.setattr(migrate_module, "FIND_LIMIT_SECONDS", 0)
    with respx.mock(assert_all_called=False) as router, pytest.raises(InstallUnknown) as info:
        run_watch(router, running_seq=[[]] * 3, job_seq=[])
    assert info.value.exit_code == 6
    assert "an install job" in info.value.message
    assert "fcm site-show erp.acme.example.com" in info.value.hint
