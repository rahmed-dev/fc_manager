# Tasks

## 1. Store field and file store

- [x] 1.1 Add `store` to `config.Profile` (default `keyring`), write it in `to_toml()` only for `file`, and refuse an unknown value in `load()` (design D1). Verify with tests in `tests/test_profiles.py`: round trip of a file profile, an old config with no store loads as `keyring`, an unknown store is a usage error.
- [x] 1.2 Add the credentials file store to `src/fc_manager/credentials.py`: path, atomic 0600 write that keeps other entries, read with the permission check, entry delete (design D2). Make `load()` and `delete()` take the store (design D4). Verify with tests: the mode is 0600, two profiles share the file, a 0644 file is refused with a `chmod 600` hint, a missing entry gives the `--replace` hint, a file load reads no keyring.

## 2. Setup and profile commands

- [x] 2.1 Move the keyring check in `add_profile()` to after the FC check, with the file question and `KeyringDeclined` (design D3). Remove the keyring check from `_precheck()` and `first_run()`. Keep the env-variable hint for `KeyringDeclined` in `first_run()`. Verify with tests in `tests/test_first_run.py` and `tests/test_profiles.py`: broken keyring plus yes saves a file profile and opens the menu; broken keyring plus no saves nothing, exits 2 and names `FCM_API_KEY`; working keyring asks no file question; prompts come before the keyring message.
- [x] 2.2 Pass `profile.store` in `resolve()`, `profile-test` and `profile-remove`. Handle `--replace` across stores (spec "Replace moves the store"). Add the `Store` column and the JSON field to `profile-list`. Verify with tests: remove of a file profile keeps other entries and does not touch the keyring; replace from file to keyring leaves no file entry; `profile-list` shows `file`.
- [x] 2.3 Update or remove the old tests that expect a stop before the prompts. Verify: `uv run pytest`, then `uv run ruff check . && uv run ruff format --check .`.

## 3. Docs and release

- [x] 3.1 Rewrite the README section "Keyring on a headless Linux host" and the "Keyring only" and "No keyring?" bullets (design D5). Remove the gnome-keyring steps. Update the install tag to `v1.2.0`. Verify that the section title still matches `credentials.README_SECTION`.
- [x] 3.2 Add `## [1.2.0]` to `CHANGELOG.md` and set `version = "1.2.0"`. Verify with `uv run fcm --version`.
- [ ] 3.3 Manual check on this host by Riz: run `fcm`, enter the new key, answer `y`, and see the menu. Then run `fcm profile-list` and see the store `file`.

## Workflow follow-up

- Commit, tag `v1.2.0`, push, and update the live install with `uv tool install --force` (approved by Riz on 2026-11-10).
- Archive the change after task 3.3.
