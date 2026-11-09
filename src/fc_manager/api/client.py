"""Frappe Cloud API client.

All FC endpoint knowledge lives in this package. The client calls only methods on its 2
allowlists: `call()` sends GET for read methods, and `write()` sends POST for write methods.
A call to any other method fails before any network request. A write is never retried.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx

from fc_manager.api.errors import map_response_error
from fc_manager.errors import (
    MethodNotAllowed,
    NetworkError,
    ServerError,
    UsageError,
    WriteUnknown,
)
from fc_manager.redact import Credentials, redact

# FC moved its API from frappecloud.com to cloud.frappe.io (the old host answers 308).
DEFAULT_BASE_URL = "https://cloud.frappe.io"

READ_ONLY_METHODS: frozenset[str] = frozenset(
    {
        "press.api.account.get",
        "press.api.client.get",
        "press.api.bench.all",
        "press.api.bench.deploy_information",
        "press.api.bench.deploy_status",
        "press.api.site.all",
        "press.api.site.get",
        "press.api.site.installed_apps",
    }
)

# Methods that change FC. Only `FCClient.write()` sends them, as POST, with no retry.
WRITE_METHODS: frozenset[str] = frozenset({"press.api.bench.deploy_and_update"})

# press.api.client.get reads any doctype the user may see. fcm allows it for these only.
READ_DOCTYPES: frozenset[str] = frozenset({"Deploy Candidate Build"})


def check_read_method(method: str, params: dict[str, Any]) -> None:
    """Raise MethodNotAllowed unless `method` (and, for client.get, its doctype) is allowed."""
    if method not in READ_ONLY_METHODS:
        raise MethodNotAllowed(f"FC method is not on the read-only allowlist: {method}")
    if method == "press.api.client.get" and params.get("doctype") not in READ_DOCTYPES:
        raise MethodNotAllowed(
            f"FC doctype is not on the read-only allowlist: {params.get('doctype')}"
        )


DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_RETRIES = 2
BACKOFF_SECONDS = (0.5, 1.5)


def validate_base_url(url: str) -> str:
    """Return the normalized base URL, or raise UsageError if it is not HTTPS."""
    url = (url or "").strip().rstrip("/")
    if not url.lower().startswith("https://"):
        raise UsageError(
            f"Base URL must use HTTPS: {url or '(empty)'}",
            hint=f"Use an https:// URL, for example {DEFAULT_BASE_URL}",
        )
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise UsageError(f"Base URL is not valid: {url}") from exc
    if not parsed.host:
        raise UsageError(f"Base URL has no host: {url}")
    return url


class FCClient:
    """Read-only client for the Frappe Cloud (press) API."""

    def __init__(
        self,
        credentials: Credentials,
        base_url: str = DEFAULT_BASE_URL,
        *,
        profile: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        debug: Callable[[str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = validate_base_url(base_url)
        self.profile = profile
        self._credentials = credentials
        self._debug = debug
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            verify=True,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "fc_manager"},
        )

    @property
    def host(self) -> str:
        return httpx.URL(self.base_url).host

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FCClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def call(self, method: str, team: str | None = None, **params: Any) -> Any:
        """Call one allowlisted FC read method and return its `message` payload."""
        check_read_method(method, params)
        query = {
            key: json.dumps(value) if isinstance(value, dict | list) else value
            for key, value in params.items()
            if value is not None
        }
        attempt = 0
        while True:
            try:
                return self._send("GET", method, team, query=query)
            except (NetworkError, ServerError):
                if attempt >= MAX_RETRIES:
                    raise
                self._sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
                attempt += 1

    def write(self, method: str, team: str, **body: Any) -> Any:
        """Send one allowlisted FC write method as POST and return its `message` payload.

        A write is never retried: a second request could start a second deploy. When FC
        does not confirm the request (timeout or 5xx), the result on FC is not known."""
        if method not in WRITE_METHODS:
            raise MethodNotAllowed(f"FC method is not on the write allowlist: {method}")
        if not team:
            raise MethodNotAllowed(f"A write needs a team: {method}")
        bench = body.get("name")
        hint = f"Run: fcm bench-show {bench}" if bench else "Check the FC dashboard."
        try:
            return self._send("POST", method, team, body=body)
        except NetworkError as exc:
            if exc.__cause__ is not None and isinstance(
                exc.__cause__, httpx.ConnectError | httpx.ConnectTimeout
            ):
                exc.hint = f"Nothing reached FC. {exc.hint or ''}".strip()
                raise
            raise WriteUnknown(
                f"FC did not confirm the request ({method}). Its result on FC is not known.",
                target=exc.target,
                hint=hint,
            ) from exc
        except ServerError as exc:
            raise WriteUnknown(
                f"FC did not confirm the request ({method}). Its result on FC is not known.",
                target=exc.target,
                hint=hint,
                server_message=exc.server_message,
            ) from exc

    def _send(
        self,
        verb: str,
        method: str,
        team: str | None,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        target = f"team {team}" if team else None
        headers = {"Authorization": self._credentials.authorization()}
        if team:
            headers["X-Press-Team"] = team
        self._log(f"-> {verb} {method} team={team or '-'} headers={headers}")
        started = time.monotonic()
        try:
            response = self._http.request(
                verb, f"/api/method/{method}", params=query, json=body, headers=headers
            )
        except httpx.TimeoutException as exc:
            self._log(f"<- timeout {method} after {time.monotonic() - started:.2f}s")
            raise NetworkError(
                f"Request to {self.host} timed out ({method})",
                target=target,
                hint="Check the network, then try again.",
            ) from exc
        except httpx.TransportError as exc:
            self._log(f"<- network error {method}: {type(exc).__name__}")
            raise NetworkError(
                f"Cannot reach {self.host} ({type(exc).__name__})",
                target=target,
                hint="Check the network and the profile base URL.",
            ) from exc

        elapsed = time.monotonic() - started
        self._log(f"<- {response.status_code} {method} team={team or '-'} {elapsed:.2f}s")

        if response.is_redirect:
            raise self._redirect_error(response, method, target)

        if response.is_success:
            try:
                data = response.json()
            except ValueError as exc:
                raise ServerError(
                    f"FC returned a response that is not JSON for {method}",
                    target=target,
                    server_message=redact(response.text[:200]),
                ) from exc
            return data.get("message") if isinstance(data, dict) else data

        raise map_response_error(response, method=method, team=team, profile=self.profile)

    def _redirect_error(self, response: httpx.Response, method: str, target: str | None):
        """Redirects are never followed: the credentials must not go to a host the user
        did not choose. Name the new host and the fix instead."""
        location = response.headers.get("location", "")
        new = httpx.URL(location) if location else None
        if new is not None and new.host and new.host != self.host:
            new_base = f"{new.scheme}://{new.host}"
            if self.profile:
                hint = f"Run: fcm profile-add {self.profile} --base-url {new_base} --replace"
            else:
                hint = f"Use a profile with --base-url {new_base}, or update fcm."
            return UsageError(
                f"FC moved: {self.host} redirects to {new.host} ({method})",
                target=target,
                hint=hint,
            )
        return ServerError(
            f"FC answered with an unexpected redirect HTTP {response.status_code} ({method})",
            target=target,
            server_message=redact(location) if location else None,
        )

    def _log(self, line: str) -> None:
        if self._debug is not None:
            self._debug(redact(line))
