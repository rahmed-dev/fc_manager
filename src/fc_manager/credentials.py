"""Credential storage and profile selection.

Secrets live in the OS keyring only, as one JSON entry per profile. Environment variables
are the only fallback. The tool never writes a secret to a plain file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import keyring
import keyring.errors
from keyring.backend import KeyringBackend

from fc_manager.api.client import DEFAULT_BASE_URL
from fc_manager.config import Config
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


def keyring_usable(backend: KeyringBackend | None = None) -> bool:
    backend = backend or keyring.get_keyring()
    children = getattr(backend, "backends", None)
    if children is not None:  # ChainerBackend
        return any(keyring_usable(child) for child in children)
    return _backend_name(backend) not in _UNSAFE_BACKENDS


def _require_keyring() -> None:
    if not keyring_usable():
        raise UsageError(
            "No secure OS keyring is available on this host",
            hint=ENV_HINT,
        )


def store(profile: str, creds: Credentials) -> None:
    _require_keyring()
    value = json.dumps({"api_key": creds.api_key, "api_secret": creds.api_secret})
    try:
        keyring.set_password(SERVICE, profile, value)
    except keyring.errors.KeyringError as exc:
        raise UsageError(
            f"Cannot write to the OS keyring: {type(exc).__name__}", hint=ENV_HINT
        ) from exc


def load(profile: str) -> Credentials:
    _require_keyring()
    try:
        value = keyring.get_password(SERVICE, profile)
    except keyring.errors.KeyringError as exc:
        raise UsageError(
            f"Cannot read the OS keyring: {type(exc).__name__}", hint=ENV_HINT
        ) from exc
    if not value:
        raise UsageError(
            f"No credentials in the keyring for profile {profile}",
            target=f"profile {profile}",
            hint=f"Run: fcm profile add {profile} --replace",
        )
    try:
        data = json.loads(value)
        return Credentials(data["api_key"], data["api_secret"])
    except (ValueError, KeyError, TypeError) as exc:
        raise UsageError(
            f"The keyring entry for profile {profile} is damaged",
            hint=f"Run: fcm profile add {profile} --replace",
        ) from exc


def delete(profile: str) -> None:
    try:
        keyring.delete_password(SERVICE, profile)
    except keyring.errors.PasswordDeleteError:
        pass  # already gone
    except keyring.errors.KeyringError as exc:
        reason = type(exc).__name__
        raise UsageError(f"Cannot remove the keyring entry ({reason})") from exc


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
            hint=f"Run: fcm profile add {name}",
        )

    env = env_credentials()
    if env is not None:
        base_url = config.profiles[name].base_url if name in config.profiles else DEFAULT_BASE_URL
        return ActiveProfile(label=name or "env", base_url=base_url, credentials=env, from_env=True)

    if not name:
        raise UsageError("No profile is set up", hint="Run: fcm profile add <name>")
    profile = config.profiles[name]
    return ActiveProfile(
        label=name, base_url=profile.base_url, credentials=load(name), from_env=False
    )
