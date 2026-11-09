import httpx
import pytest
import respx

from fc_manager.api.client import FCClient, validate_base_url
from fc_manager.errors import (
    AuthError,
    MethodNotAllowed,
    NetworkError,
    PermissionDenied,
    RateLimited,
    ServerError,
    UsageError,
    ValidationFailed,
)
from fc_manager.redact import Credentials

from .conftest import fixture, method_url

KEY, SECRET = "key-1111aaaa", "secret-2222bbbb"


def make_client(**kwargs) -> FCClient:
    kwargs.setdefault("sleep", lambda _s: None)
    return FCClient(Credentials(KEY, SECRET), profile="work", **kwargs)


# --- 2.4: headers, allowlist, HTTPS ---------------------------------------------------


@respx.mock
def test_sends_auth_and_team_headers():
    route = respx.get(method_url("press.api.bench.all")).respond(json=fixture("bench_all.json"))
    rows = make_client().call("press.api.bench.all", team="team-acme")
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Token {KEY}:{SECRET}"
    assert request.headers["X-Press-Team"] == "team-acme"
    assert rows[0]["name"] == "group-2"


@respx.mock
def test_no_team_header_without_team():
    route = respx.get(method_url("press.api.account.get")).respond(json=fixture("account_get.json"))
    make_client().call("press.api.account.get")
    assert "X-Press-Team" not in route.calls.last.request.headers


@respx.mock
def test_dict_params_are_json_encoded():
    route = respx.get(method_url("press.api.site.all")).respond(json={"message": []})
    make_client().call("press.api.site.all", team="t", site_filter={"status": "Active", "tag": ""})
    assert route.calls.last.request.url.params["site_filter"] == '{"status": "Active", "tag": ""}'


def test_method_not_on_allowlist_sends_nothing():
    with respx.mock(assert_all_called=False) as router:
        catch_all = router.route().respond(json={"message": "ok"})
        with pytest.raises(MethodNotAllowed):
            make_client().call("press.api.bench.deploy", team="t")
        assert not catch_all.called


@pytest.mark.parametrize("url", ["http://example.com", "ftp://x", "", "example.com"])
def test_rejects_non_https_base_url(url):
    with pytest.raises(UsageError):
        validate_base_url(url)


def test_accepts_https_base_url():
    assert validate_base_url("https://cloud.frappe.io/") == "https://cloud.frappe.io"


def test_client_rejects_http_base_url():
    with pytest.raises(UsageError):
        FCClient(Credentials(KEY, SECRET), "http://cloud.frappe.io")


# --- 2.5: error mapping and retries ---------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "error", "message"),
    [
        # Real FC bodies (2026-11-09): a wrong secret is 401 with exc_type only, and an
        # unknown site is 403 PermissionError "Not Permitted", not 404.
        (401, "error_auth.json", AuthError, None),
        (403, "error_not_found.json", PermissionDenied, "Not Permitted"),
        (403, "error_permission.json", PermissionDenied, "Not Permitted"),
    ],
)
@respx.mock
def test_error_fixtures_map_to_kinds(status, body, error, message):
    respx.get(method_url("press.api.site.get")).respond(status, json=fixture(body))
    with pytest.raises(error) as info:
        make_client().call("press.api.site.get", team="team-acme", name="x")
    assert info.value.server_message == message


@pytest.mark.parametrize(
    ("status", "error"),
    [(417, ValidationFailed), (429, RateLimited), (500, ServerError), (503, ServerError)],
)
@respx.mock
def test_status_codes_map_to_kinds(status, error):
    respx.get(method_url("press.api.site.all")).respond(status, json={"message": "nope"})
    with pytest.raises(error):
        make_client().call("press.api.site.all", team="t")


@respx.mock
def test_auth_error_hint_names_profile():
    respx.get(method_url("press.api.account.get")).respond(401, json=fixture("error_auth.json"))
    with pytest.raises(AuthError) as info:
        make_client().call("press.api.account.get")
    assert info.value.hint and "fcm profile add work --replace" in info.value.hint
    assert info.value.target == "profile work"


@respx.mock
def test_permission_error_names_team():
    respx.get(method_url("press.api.site.all")).respond(403, json=fixture("error_permission.json"))
    with pytest.raises(PermissionDenied) as info:
        make_client().call("press.api.site.all", team="client-x")
    assert "client-x" in info.value.message


@respx.mock
def test_non_json_error_body_falls_back_to_status_and_snippet():
    respx.get(method_url("press.api.site.all")).respond(502, text="<html>Bad gateway</html>")
    with pytest.raises(ServerError) as info:
        make_client().call("press.api.site.all", team="t")
    assert info.value.server_message.startswith("HTTP 502")


@respx.mock
def test_502_then_200_succeeds():
    route = respx.get(method_url("press.api.site.all"))
    route.side_effect = [httpx.Response(502), httpx.Response(200, json={"message": []})]
    assert make_client().call("press.api.site.all", team="t") == []
    assert route.call_count == 2


@respx.mock
def test_server_error_retried_at_most_twice():
    route = respx.get(method_url("press.api.site.all")).respond(500)
    with pytest.raises(ServerError):
        make_client().call("press.api.site.all", team="t")
    assert route.call_count == 3


@respx.mock
def test_auth_error_is_not_retried():
    route = respx.get(method_url("press.api.account.get")).respond(
        401, json=fixture("error_auth.json")
    )
    with pytest.raises(AuthError):
        make_client().call("press.api.account.get")
    assert route.call_count == 1


@respx.mock
def test_timeout_gives_network_error_naming_host():
    respx.get(method_url("press.api.account.get")).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(NetworkError) as info:
        make_client().call("press.api.account.get")
    assert "cloud.frappe.io" in info.value.message


@respx.mock
def test_connect_error_gives_network_error():
    respx.get(method_url("press.api.account.get")).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(NetworkError):
        make_client().call("press.api.account.get")


# --- 2.6: debug log -------------------------------------------------------------------


@respx.mock
def test_debug_log_shows_method_team_status_duration_and_redacts():
    respx.get(method_url("press.api.site.all")).respond(json={"message": []})
    lines: list[str] = []
    make_client(debug=lines.append).call("press.api.site.all", team="team-acme")
    text = "\n".join(lines)
    assert "press.api.site.all" in text
    assert "team=team-acme" in text
    assert "<- 200" in text
    assert "s" in text.split("<- 200")[1]  # duration in seconds
    assert "Authorization" in text
    assert KEY not in text and SECRET not in text


# --- redirects ------------------------------------------------------------------------


@respx.mock
def test_redirect_to_new_host_is_a_usage_error_with_the_fix():
    old = "https://frappecloud.com"
    route = respx.get(f"{old}/api/method/press.api.account.get").respond(
        308, headers={"location": "https://cloud.frappe.io/api/method/press.api.account.get"}
    )
    new_route = respx.get(method_url("press.api.account.get")).respond(json={"message": {}})
    with pytest.raises(UsageError) as info:
        make_client(base_url=old).call("press.api.account.get")
    assert "cloud.frappe.io" in info.value.message
    assert "fcm profile add work --base-url https://cloud.frappe.io --replace" in info.value.hint
    assert route.call_count == 1  # not retried
    assert not new_route.called  # the credentials never followed the redirect


@respx.mock
def test_same_host_redirect_is_a_server_error():
    respx.get(method_url("press.api.site.all")).respond(
        302, headers={"location": "https://cloud.frappe.io/login"}
    )
    with pytest.raises(ServerError):
        make_client().call("press.api.site.all", team="t")
