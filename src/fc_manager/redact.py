"""Secret redaction.

Every path that writes text the user can see (errors, debug output, tracebacks) passes
through `redact()`. Credentials register their values here when they are created.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

MASK = "***"
_MIN_SECRET_LEN = 4

_lock = threading.Lock()
_secrets: set[str] = set()

# `Authorization: Token key:secret`, `"Authorization": "token ..."`, `authorization=...`
_AUTH_RE = re.compile(
    r"""(?ix)
    (authorization['"]?\s*[:=]\s*['"]?)   # header name and separator
    (?:(token|bearer|basic)\s+)?          # optional scheme
    [^\s'",}]+                            # the credential value
    """
)


def register(*values: str) -> None:
    """Register secret values so `redact()` masks them."""
    with _lock:
        for value in values:
            if value and len(value) >= _MIN_SECRET_LEN:
                _secrets.add(value)


def clear() -> None:
    """Forget all registered secrets (used by tests)."""
    with _lock:
        _secrets.clear()


def redact(text: str) -> str:
    """Return `text` with registered secrets and Authorization values masked."""
    if not text:
        return text
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, MASK)

    def _mask_auth(match: re.Match[str]) -> str:
        scheme = f"{match.group(2)} " if match.group(2) else ""
        return f"{match.group(1)}{scheme}{MASK}"

    return _AUTH_RE.sub(_mask_auth, text)


@dataclass(frozen=True, slots=True, repr=False)
class Credentials:
    """One FC API key and secret. Never shows its values in repr() or str()."""

    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    def __post_init__(self) -> None:
        register(self.api_key, self.api_secret)

    def authorization(self) -> str:
        return f"Token {self.api_key}:{self.api_secret}"

    def __repr__(self) -> str:
        return f"Credentials(api_key={MASK}, api_secret={MASK})"

    __str__ = __repr__
