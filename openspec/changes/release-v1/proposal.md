# Proposal

## Why

`fcm` is ready for its first public release. Today a user must clone the repo, and must know to run `fcm profile-add` before the menu works. The repo also lacks a licence, a changelog, a version option and install docs for a global install.

## What Changes

- First-run setup: on a terminal, `fcm` with no command, no profile and no environment credentials asks for a profile name, the FC API key and the API secret. It checks them with FC, stores them as a profile, and opens the menu.
- New option `fcm --version`: prints `fcm <version>` and exits with code 0.
- Version 1.0.0. MIT `LICENSE` file, and the licence, the authors and the project URLs in `pyproject.toml`.
- `CHANGELOG.md` with the 1.0.0 entry.
- README: global install from the GitHub tag with `uv tool install` (and `pipx`), the first run, upgrade and uninstall.
- CI: build the wheel and check that it holds only the package and its metadata.
- Dev helper `bin/fcm-first-run`: runs `fcm` with an empty, temporary config and no environment credentials, so the maintainer can live-check the first-run setup. It removes the test profile at exit.
- Out of scope: PyPI publishing; the history rewrite, the push, the tag and the GitHub release (done after this change, each step with the maintainer's approval).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `credential-profiles`: a first-run setup that adds the first profile from the menu entry.
- `cli-output`: a `--version` option.

## Impact

- Code: `cli/menu.py` (first-run check, `--version`), `cli/profile.py` (shared add function), `pyproject.toml`.
- New files: `LICENSE`, `CHANGELOG.md`, `bin/fcm-first-run`, `scripts/check_wheel.py`.
- CI: `.github/workflows/ci.yml` gets a wheel check step.
- Tests: first-run setup, `--version`, wheel content script.
- Docs: `README.md`.
- FC: the setup sends the same read-only check as `profile-add`. No write.
