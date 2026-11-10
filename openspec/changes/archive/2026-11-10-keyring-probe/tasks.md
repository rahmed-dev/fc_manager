# Tasks

## 1. Keyring probe

- [x] 1.1 In `src/fc_manager/credentials.py`, extend `keyring_usable()` with the probe read of `(SERVICE, "__fcm_probe__")` after the class-name test (design D1). Any exception means "not usable". Verify with new tests in `tests/test_profiles.py`: a fake backend that raises `InitError` on `get_password` gives `False`; `MemoryKeyring` gives `True`; the fake store holds no entry after the probe.
- [x] 1.2 Keep the probe result for the rest of the process (design D2), and add an autouse fixture in `tests/conftest.py` that resets it. Verify with a test that counts probe reads: `fcm profile-add` with a valid key reads the probe entry once.
- [x] 1.3 Make sure a fake backend that raises a non-keyring exception (for example `OSError`) on the read also gives `False`. Verify with a test in `tests/test_profiles.py`.

## 2. Plain cause in errors

- [x] 2.1 Add the helper that maps an exception to the cause text and the Linux README hint (design D4). Use it in `_require_keyring()`, `store()`, `load()` and `delete()`. Verify with parametrized tests for `InitError`, `KeyringLocked`, `NoKeyringError` and `RuntimeError`: the message holds the cause text, the hint holds `FCM_API_KEY` and `FCM_API_SECRET`, and no key or secret appears.
- [x] 2.2 Use the same message and hint in `first_run()` (`cli/menu.py`) and `_precheck()` (`cli/profile.py`). Verify with a test in `tests/test_first_run.py`: a fake backend that raises `InitError` on read gives exit code 2, no prompt (`asked == []`), no menu, and the cause text in stderr. Add the same test for `fcm profile-add work` in `tests/test_profiles.py`.
- [x] 2.3 Verify that the existing tests still pass: `uv run pytest`, then `uv run ruff check . && uv run ruff format --check .`.

## 3. Docs and release

- [x] 3.1 Replaced by change `credential-file-fallback` (2026-11-10). The gnome-keyring steps did not work on this host: `gnome-keyring-daemon --unlock` started a second daemon and the running daemon could not open the new login keyring. The new change removes these steps from the README.
- [x] 3.2 In `README.md`, extend "No keyring?" with the case "keyring daemon runs, but no login keyring", and add the section "Keyring on a headless Linux host" with the env-variable path first and the checked gnome-keyring steps second. Say that the installed `fcm` does not read the `.env` file of `bin/fcm-dev`. Verify that the section title matches the CLI hint text exactly.
- [x] 3.3 Add a `## [1.1.1]` entry under `### Fixed` in `CHANGELOG.md`, and set `version = "1.1.1"` in `pyproject.toml`. Verify with `uv run fcm --version`.
- [x] 3.4 Manual check on this host, with `FCM_API_KEY` and `FCM_API_SECRET` unset and no login keyring: `uv run fcm` asks for nothing, prints the plain cause and the hint, and exits with code 2. Riz runs it and reports the output.

## Workflow follow-up

- Riz revokes the FC API key that was pasted in the chat on 2026-11-10, and makes a new one.
- Archive the change with `/opsx:archive` after the review and the manual check.
