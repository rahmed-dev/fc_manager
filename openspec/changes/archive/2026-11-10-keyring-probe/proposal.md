# Proposal

## Why

On a headless Linux server, `fcm` asks for the API key and the API secret, and then fails with `Cannot write to the OS keyring: InitError`. The cause: `gnome-keyring-daemon` runs, so keyring picks the Secret Service backend. But no `login` keyring exists, and gnome-keyring cannot show the password prompt that makes one. The check `keyring_usable()` looks only at the backend class name, so it passes. The user types the key for nothing, and the error does not say what is wrong.

## What Changes

- The keyring check does a real read of a probe entry with the active backend. A backend that raises an error on that read counts as not usable. The class-name check stays as the first test.
- The first-run setup and `fcm profile-add` run this check before any prompt. On failure they ask for nothing and exit with code 2. This is what the spec already says for "no keyring"; the check now detects this case too.
- The error names the cause in plain words. For example: the keyring is locked, or it has no default collection and cannot prompt for one. It does not only show the exception class name.
- The hint names the `FCM_API_KEY` and `FCM_API_SECRET` path. On Linux it also points to the README section that tells how to make and unlock a login keyring on a headless host.
- A keyring read error for a stored profile (`load`) uses the same plain cause and hint.
- README: the "No keyring?" section covers the case "keyring daemon runs, but it has no login keyring". It also says that the installed `fcm` does not read the `.env` file of `bin/fcm-dev`.
- Storage stays keyring only. No file fallback.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `credential-profiles`: "Secrets stored only in the OS keyring" and "First-run setup steps" change. A keyring is usable only when a real read works. The "no keyring" error names the cause and the fix.

## Impact

- Code: `src/fc_manager/credentials.py` (`keyring_usable`, a new probe, the error text of `store`, `load` and `delete`). `src/fc_manager/cli/menu.py` (`first_run`) and `src/fc_manager/cli/profile.py` (`_precheck`) use the new check.
- Tests: `tests/test_profiles.py` and `tests/test_first_run.py`, with a fake backend that raises `InitError` and `KeyringLocked` on a read.
- Docs: `README.md` and `CHANGELOG.md` (patch release 1.1.1).
- No new dependency. No change to the config file or to the FC API calls.
- Desktop hosts: the probe read can show an unlock prompt for a locked login keyring before the key prompt. Today that prompt comes at the write, after the key prompt.
