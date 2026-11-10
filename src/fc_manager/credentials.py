"""Credential storage and profile selection.

Secrets live in the OS keyring, as one JSON entry per profile. When no keyring works, and
only after the user says yes, they live in the credentials file (mode 0600) next to the
config file. Environment variables win over both stores.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import keyring
import keyring.errors
import tomli_w
from keyring.backend import KeyringBackend

from fc_manager import config as config_file
from fc_manager.api.client import DEFAULT_BASE_URL
from fc_manager.config import STORE_FILE, STORE_KEYRING, Config
from fc_manager.errors import UsageError
from fc_manager.redact import Credentials

SERVICE = "fc_manager"
ENV_KEY = "FCM_API_KEY"
ENV_SECRET = "FCM_API_SECRET"  # noqa: S105 - variable name, not a secret
ENV_PROFILE = "FCM_PROFILE"

ENV_HINT = f"Set {ENV_KEY} and {ENV_SECRET} in the environment instead."

# Backends that do not protect a secret, or do not store anything.
_UNSAFE_BACKENDS = {
    "keyring.backends.fail.Keyring",
    "keyring.backends.null.Keyring",
    "keyrings.alt.file.PlaintextKeyring",
}


def _backend_name(backend: KeyringBackend) -> str:
    cls = type(backend)
    return f"{cls.__module__}.{cls.__qualname__}"


def _safe_class(backend: KeyringBackend) -> bool:
    children = getattr(backend, "backends", None)
    if children is not None:  # ChainerBackend
        return any(_safe_class(child) for child in children)
    return _backend_name(backend) not in _UNSAFE_BACKENDS


# The probe reads this entry. It holds no secret, and the probe never writes it.
PROBE_ENTRY = "__fcm_probe__"
# The probe result for this process: (backend, cause), cause None when the read worked.
_probe: tuple[KeyringBackend, str | None] | None = None

README_SECTION = "Keyring on a headless Linux host"


def reset_probe() -> None:
    """Forget the probe result (for tests)."""
    global _probe
    _probe = None


def keyring_cause(exc: BaseException) -> str:
    """The plain cause of a keyring failure, to end the sentence
    'The OS keyring on this host <cause>'."""
    if isinstance(exc, keyring.errors.KeyringLocked):
        return "is locked"
    if isinstance(exc, keyring.errors.NoKeyringError):
        return "has no backend"
    if isinstance(exc, keyring.errors.InitError):
        return (
            "cannot open its default keyring "
            "(no login keyring exists, and the keyring cannot prompt for one)"
        )
    return f"does not work ({type(exc).__name__})"


def keyring_hint() -> str:
    if sys.platform.startswith("linux"):
        return f'{ENV_HINT} See the README: "{README_SECTION}".'
    return ENV_HINT


def keyring_problem(backend: KeyringBackend | None = None) -> str | None:
    """None when the keyring works, else the cause. The check is one read of
    PROBE_ENTRY, done once per process for a backend. It never writes."""
    global _probe
    backend = backend or keyring.get_keyring()
    if not _safe_class(backend):
        return "has no secure backend"
    if _probe is not None and _probe[0] is backend:
        return _probe[1]
    try:
        backend.get_password(SERVICE, PROBE_ENTRY)
        cause = None
    except Exception as exc:  # noqa: BLE001 - any failure means the secret cannot be kept
        cause = keyring_cause(exc)
    _probe = (backend, cause)
    return cause


def keyring_usable(backend: KeyringBackend | None = None) -> bool:
    return keyring_problem(backend) is None


def keyring_error(lead: str | None = None) -> UsageError:
    """The 'no keyring' error, with the cause of the last check."""
    cause = keyring_problem() or "is not usable"
    message = f"The OS keyring on this host {cause}"
    if lead:
        message = f"{lead}. {message}"
    return UsageError(message, hint=keyring_hint())


class KeyringDeclined(UsageError):
    """No keyring works, and the user did not want the credentials file. Nothing saved."""


def _failure(action: str, exc: BaseException) -> UsageError:
    return UsageError(
        f"Cannot {action} the OS keyring. The OS keyring on this host {keyring_cause(exc)}",
        hint=keyring_hint(),
    )


def _require_keyring() -> None:
    if not keyring_usable():
        raise keyring_error()


def store(profile: str, creds: Credentials) -> None:
    _require_keyring()
    value = json.dumps({"api_key": creds.api_key, "api_secret": creds.api_secret})
    try:
        keyring.set_password(SERVICE, profile, value)
    except keyring.errors.KeyringError as exc:
        raise _failure("write to", exc) from exc


def _missing(profile: str, where: str) -> UsageError:
    return UsageError(
        f"No credentials in the {where} for profile {profile}",
        target=f"profile {profile}",
        hint=f"Run: fcm profile-add {profile} --replace",
    )


def _parse(profile: str, value: str, where: str) -> Credentials:
    try:
        data = json.loads(value)
        return Credentials(data["api_key"], data["api_secret"])
    except (ValueError, KeyError, TypeError) as exc:
        raise UsageError(
            f"The {where} entry for profile {profile} is damaged",
            hint=f"Run: fcm profile-add {profile} --replace",
        ) from exc


def load(profile: str, store: str = STORE_KEYRING) -> Credentials:
    if store == STORE_FILE:
        return _file_load(profile)
    _require_keyring()
    try:
        value = keyring.get_password(SERVICE, profile)
    except keyring.errors.KeyringError as exc:
        raise _failure("read", exc) from exc
    if not value:
        raise _missing(profile, "keyring")
    return _parse(profile, value, "keyring")


def delete(profile: str, store: str = STORE_KEYRING) -> None:
    if store == STORE_FILE:
        _file_delete(profile)
        return
    try:
        keyring.delete_password(SERVICE, profile)
    except keyring.errors.PasswordDeleteError:
        pass  # already gone
    except keyring.errors.KeyringError as exc:
        raise _failure("remove the entry from", exc) from exc


# --- credentials file: only when no keyring works, and only after the user says yes ---


def file_path() -> Path:
    return config_file.config_path().parent / "credentials"


def _file_read() -> dict[str, dict]:
    path = file_path()
    if not path.exists():
        return {}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise UsageError(
            f"The credentials file {path} can be read by other users (mode {mode:04o})",
            hint=f"Run: chmod 600 {path}",
        )
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise UsageError(f"Cannot read the credentials file {path}: {exc}") from exc
    profiles = data.get("profiles") or {}
    return profiles if isinstance(profiles, dict) else {}


def _file_write(profiles: dict[str, dict]) -> None:
    """Write the credentials file atomically with mode 0600 (directory 0700)."""
    path = file_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name("credentials.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        tomli_w.dump({"profiles": profiles}, handle)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def file_store(profile: str, creds: Credentials) -> None:
    profiles = _file_read()
    profiles[profile] = {"api_key": creds.api_key, "api_secret": creds.api_secret}
    _file_write(profiles)


def _file_load(profile: str) -> Credentials:
    entry = _file_read().get(profile)
    if not entry:
        raise _missing(profile, "credentials file")
    return _parse(profile, json.dumps(entry), "credentials file")


def _file_delete(profile: str) -> None:
    profiles = _file_read()
    if profiles.pop(profile, None) is None:
        return  # already gone
    if profiles:
        _file_write(profiles)
    else:
        file_path().unlink(missing_ok=True)


def env_credentials() -> Credentials | None:
    key = os.environ.get(ENV_KEY) or ""
    secret = os.environ.get(ENV_SECRET) or ""
    if key and secret:
        return Credentials(key, secret)
    if key or secret:
        missing = ENV_SECRET if key else ENV_KEY
        raise UsageError(
            f"{missing} is not set, but {ENV_KEY if key else ENV_SECRET} is",
            hint=f"Set both {ENV_KEY} and {ENV_SECRET}, or unset both.",
        )
    return None


@dataclass(frozen=True)
class ActiveProfile:
    label: str
    base_url: str
    credentials: Credentials
    from_env: bool


def resolve(profile_option: str | None, config: Config) -> ActiveProfile:
    """Pick the credentials for this run (env vars win over the keyring)."""
    name = profile_option or os.environ.get(ENV_PROFILE) or config.default_profile
    if name and name not in config.profiles and env_credentials() is None:
        known = ", ".join(sorted(config.profiles)) or "none"
        raise UsageError(
            f"Profile {name} does not exist (profiles: {known})",
            hint=f"Run: fcm profile-add {name}",
        )

    env = env_credentials()
    if env is not None:
        base_url = config.profiles[name].base_url if name in config.profiles else DEFAULT_BASE_URL
        return ActiveProfile(label=name or "env", base_url=base_url, credentials=env, from_env=True)

    if not name:
        raise UsageError("No profile is set up", hint="Run: fcm profile-add <name>")
    profile = config.profiles[name]
    return ActiveProfile(
        label=name,
        base_url=profile.base_url,
        credentials=load(name, profile.store),
        from_env=False,
    )
