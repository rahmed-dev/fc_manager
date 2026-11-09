"""Tool errors. Each error has a kind, and each kind has one exit code."""

from __future__ import annotations

from enum import StrEnum


class ErrorKind(StrEnum):
    UNEXPECTED = "unexpected"
    USAGE = "usage"
    AUTH = "authentication"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    NETWORK = "network"
    PARTIAL = "partial_failure"


EXIT_CODES: dict[ErrorKind, int] = {
    ErrorKind.UNEXPECTED: 1,
    ErrorKind.VALIDATION: 1,
    ErrorKind.USAGE: 2,
    ErrorKind.AUTH: 3,
    ErrorKind.PERMISSION: 4,
    ErrorKind.NOT_FOUND: 5,
    ErrorKind.RATE_LIMIT: 6,
    ErrorKind.SERVER: 6,
    ErrorKind.NETWORK: 6,
    ErrorKind.PARTIAL: 7,
}


class FcmError(Exception):
    """Base for every error the tool reports to the user."""

    kind: ErrorKind = ErrorKind.UNEXPECTED

    def __init__(
        self,
        message: str,
        *,
        target: str | None = None,
        hint: str | None = None,
        server_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.target = target
        self.hint = hint
        self.server_message = server_message

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.kind]


class UsageError(FcmError):
    """Wrong command use or wrong configuration (exit 2)."""

    kind = ErrorKind.USAGE


class AuthError(FcmError):
    kind = ErrorKind.AUTH


class PermissionDenied(FcmError):
    kind = ErrorKind.PERMISSION


class NotFound(FcmError):
    kind = ErrorKind.NOT_FOUND


class ValidationFailed(FcmError):
    kind = ErrorKind.VALIDATION


class RateLimited(FcmError):
    kind = ErrorKind.RATE_LIMIT


class ServerError(FcmError):
    kind = ErrorKind.SERVER


class NetworkError(FcmError):
    kind = ErrorKind.NETWORK


class PartialFailure(FcmError):
    """Some teams failed in a command that covers several teams (exit 7)."""

    kind = ErrorKind.PARTIAL

    def __init__(self, message: str, failures: list[tuple[str, FcmError]], **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.failures = failures


class MethodNotAllowed(FcmError):
    """Code asked the API client for a method outside the read-only allowlist."""

    kind = ErrorKind.UNEXPECTED
