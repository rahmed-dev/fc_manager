# Design

## Context

See proposal.md - Why. Current state:

- `fcm` with no command on a terminal runs `menu.root`, which opens a session. `credentials.resolve` raises "No profile is set up" (exit 2) when no profile and no environment credentials exist.
- `fcm profile-add NAME` prompts for the key and the hidden secret (this change makes the secret prompt visible, see D7), checks them with `Inventory.account()` (read-only), stores the secret in the keyring and the profile in the config file, and sets the default profile when none is set.
- `config.config_path()` honours `FCM_CONFIG_DIR`. Keyring entries use the service `fc_manager` and the profile name.
- `pyproject.toml`: version 0.1.0, no licence, hatchling build. The wheel holds only `fc_manager/` and its metadata (checked on 2026-11-09).
- A package cannot run code at install time (`uv tool install` and `pipx` run no install hook), so the key prompt belongs to the first run.

Release decisions by the maintainer (2026-11-09): GitHub tag only, no PyPI; MIT; repo `rahmed-dev/fc_manager`.

## Goals / Non-Goals

**Goals:**
- Install in one command, then `fcm` guides the user to a working menu.
- A version the user can read with `fcm --version`.
- Legal and docs basics for a public repo.

**Non-Goals:**
- No PyPI publish, no release workflow on tag.
- No change to the write guards or to any FC request.
- The history rewrite, push, tag and GitHub release are not part of this change.

## Decisions

### D1. Setup in the menu entry, not in `credentials.resolve`
`menu.root` checks, before the session opens: no `--profile`, no `FCM_PROFILE`, no profile in the config, and `env_credentials()` is None. Only then does it run the setup. Direct commands keep their current error and hint, so a script never gets a prompt.
- Alternative: prompt in `resolve()` for every command. Rejected: a direct command in a terminal is often part of a typed one-liner; a surprise prompt there is worse than a clear error.

### D2. One add function
The body of `profile-add` moves to `add_profile(out, name, base_url, *, debug)`. It returns the account. `profile-add` and the setup both call it. The setup prints a short welcome first, with where to make an API key in the FC dashboard, and then asks for the profile name with the default `default`. The name check (`NAME_RE`) is the same.

### D3. `--version`
An eager callback option on the root callback. It reads `importlib.metadata.version("fc-manager")` and prints `fcm <version>`. It runs before the menu and before any session.

### D4. Wheel check
`scripts/check_wheel.py PATH` lists a wheel and fails when an entry is outside `fc_manager/` and `fc_manager-<version>.dist-info/`. CI runs `uv build --wheel` and then the script. A unit test feeds the script a small synthetic wheel with a bad entry and a good one.

### D5. Live-check helper
`bin/fcm-first-run` makes a temporary config dir, unsets `FCM_API_KEY`, `FCM_API_SECRET` and `FCM_PROFILE`, and runs `uv run fcm` with `FCM_CONFIG_DIR` set to that dir. At exit, it deletes the keyring entry of every profile in that temporary config (with `fcm profile-remove NAME --yes`), then deletes the dir. The maintainer has no saved profile on this machine (checked 2026-11-09), so no real keyring entry is touched. The helper prints the profile name to use, `first-run-check`.

### D6. Packaging metadata
`license = "MIT"` and `license-files = ["LICENSE"]` (PEP 639, supported by hatchling), `authors = [{ name = "rahmed-dev" }]` with no email, and `[project.urls]` for the homepage, the issues page and the changelog.

### D7. Visible secret prompt
The secret prompt shows the typed or pasted text (maintainer decision, 2026-11-09). In the live check, a hidden paste of the wrong text could not be seen. The secret is still never a command-line argument, never in the config file, and never in any `fcm` output after the prompt.
- Alternative: keep it hidden and print a check line (length and last 4 characters). Rejected by the maintainer.

## Risks / Trade-offs

- [A visible secret stays in the terminal scrollback and in screenshots] The README says so, and tells the user to clear the screen after the setup on a shared screen. A user can revoke the key in the FC dashboard.

- [The setup stores a wrong key] The FC check runs before the store, as in `profile-add`. A rejected key stores nothing.
- [A user without a keyring is stuck at the setup] The setup checks the keyring first and names the environment variables.
- [`bin/fcm-first-run` leaves a keyring entry when it is killed] The helper uses a trap on exit. A left entry holds only the test credentials the maintainer typed, and `fcm profile-remove` can delete it.

## Migration Plan

No data migration. Existing profiles and the config file do not change. Rollback is a revert of the commit.

## Open Questions

None.
