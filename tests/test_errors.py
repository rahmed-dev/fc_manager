import pytest

from fc_manager.errors import (
    EXIT_CODES,
    AuthError,
    ErrorKind,
    FcmError,
    MethodNotAllowed,
    NetworkError,
    NotFound,
    PartialFailure,
    PermissionDenied,
    RateLimited,
    ServerError,
    UsageError,
    ValidationFailed,
)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (FcmError("x"), 1),
        (MethodNotAllowed("x"), 1),
        (ValidationFailed("x"), 1),
        (UsageError("x"), 2),
        (AuthError("x"), 3),
        (PermissionDenied("x"), 4),
        (NotFound("x"), 5),
        (NetworkError("x"), 6),
        (ServerError("x"), 6),
        (RateLimited("x"), 6),
        (PartialFailure("x", failures=[]), 7),
    ],
)
def test_exit_codes_match_cli_output_spec(error, code):
    assert error.exit_code == code


def test_every_kind_has_an_exit_code():
    assert set(EXIT_CODES) == set(ErrorKind)
