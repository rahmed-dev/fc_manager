# Proposal

## Why

Since 1.1.1, on a host where the OS keyring does not work (for example gnome-keyring with no login keyring on a headless server), the first run asks for nothing and stops. The only way forward is `FCM_API_KEY` and `FCM_API_SECRET`, which the user must put in a shell file by hand. The manual keyring steps in the README did not work on such a host (2026-11-10). The user wants the setup to ask for the key, as before, and to end with a working profile.

## What Changes

- The first run and `fcm profile-add` always ask for the profile name, the API key and the API secret, and check them with FC. A broken keyring no longer stops them before the prompts.
- If the keyring works, the system saves the key in the keyring, as today.
- If the keyring does not work, the system says why, and asks to save the key in a credentials file with mode 0600 in the config directory. The default answer is No. On No, the system saves nothing and exits with code 2, with the environment-variable hint.
- Each profile records its store (`keyring` or `file`) in the config file. Commands read the key from that store. The system refuses a credentials file that other users can read.
- `profile-remove` deletes the entry from the store of the profile. `profile-add --replace` also removes the old entry when the store changes. `profile-list` shows the store.
- **BREAKING** (rule change, not an API change): the rule "never a plain file" becomes "a plain file only after the user says yes, and only when no keyring works".
- README: the section "Keyring on a headless Linux host" drops the gnome-keyring steps and describes the file option and the environment variables.
- Version 1.2.0.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `credential-profiles`: secret storage (keyring, or a 0600 file after a yes), the keyring check moves to after the FC check, first-run "no keyring" behaviour, profile removal and the profile list.

## Impact

- Code: `src/fc_manager/credentials.py` (file store, store-aware `load` and `delete`), `src/fc_manager/config.py` (`store` field on `Profile`), `src/fc_manager/cli/profile.py` (`add_profile`, `_precheck`, `profile-list`, `profile-test`, `profile-remove`), `src/fc_manager/cli/menu.py` (`first_run`).
- Files: new `credentials` file in the config directory (`~/.config/fc_manager/credentials` on Linux), mode 0600. `config.toml` gains `store = "file"` for a file profile. Old config files stay valid: no `store` means `keyring`.
- Tests: `tests/test_profiles.py`, `tests/test_first_run.py`.
- Docs: `README.md`, `CHANGELOG.md`.
- No new dependency.
