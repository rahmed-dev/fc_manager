"""Config file: profile names and non-secret settings only. Never keys or secrets."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs
import tomli_w

from fc_manager.errors import UsageError

APP_NAME = "fc_manager"
CONFIG_DIR_ENV = "FCM_CONFIG_DIR"


def config_path() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    base = Path(override) if override else Path(platformdirs.user_config_dir(APP_NAME))
    return base / "config.toml"


@dataclass
class Profile:
    name: str
    base_url: str


@dataclass
class Config:
    default_profile: str | None = None
    profiles: dict[str, Profile] = field(default_factory=dict)

    def to_toml(self) -> dict:
        data: dict = {}
        if self.default_profile:
            data["default_profile"] = self.default_profile
        data["profiles"] = {p.name: {"base_url": p.base_url} for p in self.profiles.values()}
        return data


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise UsageError(f"Cannot read config file {path}: {exc}") from exc
    profiles = {}
    for name, values in (data.get("profiles") or {}).items():
        if not isinstance(values, dict) or "base_url" not in values:
            raise UsageError(f"Config file {path}: profile {name!r} has no base_url")
        profiles[name] = Profile(name=name, base_url=str(values["base_url"]))
    default = data.get("default_profile")
    return Config(default_profile=default if default in profiles else None, profiles=profiles)


def save(config: Config, path: Path | None = None) -> Path:
    """Write the config atomically with mode 0600 (directory 0700)."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".toml.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        tomli_w.dump(config.to_toml(), handle)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path
