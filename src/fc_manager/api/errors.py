"""Map Frappe Cloud error responses to tool errors.

FC runs on the Frappe framework. A failed call returns an HTTP error status and, most of
the time, a JSON body with some of: `exc_type`, `exception`, `_server_messages`, `message`.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

import httpx

from fc_manager.errors import (
    AuthError,
    FcmError,
    NotFound,
    PermissionDenied,
    RateLimited,
    ServerError,
    ValidationFailed,
)
from fc_manager.redact import redact

_TAG_RE = re.compile(r"<[^>]+>")
_EXC_PREFIX_RE = re.compile(r"^[\w.]+(?:Error|Exception):\s*")

_EXC_TYPES: dict[str, type[FcmError]] = {
    "AuthenticationError": AuthError,
    "PermissionError": PermissionDenied,
    "DoesNotExistError": NotFound,
    "PageDoesNotExistError": NotFound,
    "ValidationError": ValidationFailed,
    "MandatoryError": ValidationFailed,
    "RateLimitExceededError": RateLimited,
    "TooManyRequestsError": RateLimited,
}


def _clean(text: str) -> str:
    text = html.unescape(_TAG_RE.sub("", text))
    return " ".join(text.split())


def server_message(body: Any) -> str | None:
    """Pull the human message out of a Frappe error body."""
    if not isinstance(body, dict):
        return None
    raw = body.get("_server_messages")
    if isinstance(raw, str):
        try:
            items = json.loads(raw)
        except ValueError:
            items = [raw]
        messages = []
        for item in items if isinstance(items, list) else [items]:
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except ValueError:
                    messages.append(item)
                    continue
            if isinstance(item, dict) and item.get("message"):
                messages.append(str(item["message"]))
            elif isinstance(item, str):
                messages.append(item)
        if messages:
            return _clean(" ".join(messages))
    message = body.get("message")
    if isinstance(message, str) and message.strip():
        return _clean(message)
    exception = body.get("exception")
    if isinstance(exception, str) and exception.strip():
        return _clean(_EXC_PREFIX_RE.sub("", exception.strip().splitlines()[-1]))
    return None


def _error_class(status: int, exc_type: str | None) -> type[FcmError]:
    if exc_type and exc_type in _EXC_TYPES:
        return _EXC_TYPES[exc_type]
    if status == 401:
        return AuthError
    if status == 403:
        return PermissionDenied
    if status == 404:
        return NotFound
    if status == 417 or status == 400 or status == 422:
        return ValidationFailed
    if status == 429:
        return RateLimited
    return ServerError


def map_response_error(
    response: httpx.Response, *, method: str, team: str | None, profile: str | None
) -> FcmError:
    """Turn a failed FC response into the matching tool error."""
    try:
        body = response.json()
    except ValueError:
        body = None

    exc_type = body.get("exc_type") if isinstance(body, dict) else None
    message = server_message(body)
    if message is None and body is None:
        snippet = response.text[:200].strip()
        message = f"HTTP {response.status_code}: {snippet}" if snippet else None
    message = redact(message) if message else None

    cls = _error_class(response.status_code, exc_type)
    target = f"team {team}" if team else None
    who = f"profile {profile}" if profile else "FCM_API_KEY / FCM_API_SECRET"

    if cls is AuthError:
        return AuthError(
            f"FC rejected the credentials {'of' if profile else 'in'} {who}",
            target=f"profile {profile}" if profile else target,
            hint=(
                f"Make a new API key in the FC dashboard, then run: fcm profile-add {profile} "
                "--replace"
                if profile
                else "Check FCM_API_KEY and FCM_API_SECRET."
            ),
            server_message=message,
        )
    if cls is PermissionDenied:
        where = f" in team {team}" if team else ""
        return PermissionDenied(
            f"Permission denied{where} ({method})",
            target=target,
            hint="Your FC role in this team does not allow this call. Ask a team admin.",
            server_message=message,
        )
    if cls is NotFound:
        return NotFound(f"FC found nothing for {method}", target=target, server_message=message)
    if cls is RateLimited:
        return RateLimited(
            f"FC rate limit reached ({method})",
            target=target,
            hint="Wait a minute, then try again.",
            server_message=message,
        )
    if cls is ValidationFailed:
        return ValidationFailed(
            f"FC refused the request ({method})", target=target, server_message=message
        )
    return ServerError(
        f"FC server error HTTP {response.status_code} ({method})",
        target=target,
        hint="FC may be down. Try again later.",
        server_message=message,
    )
