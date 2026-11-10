# Design

## Context

See proposal.md - Why. Facts from this host (2026-11-10):

- keyring picks `keyring.backends.SecretService.Keyring` (priority 5), because `gnome-keyring-daemon` owns `org.freedesktop.secrets` on the user D-Bus.
- `~/.local/share/keyrings/` is empty. The only collection is the temporary `session` collection.
- `secretstorage.get_default_collection()` raises `PromptDismissedException`: gnome-keyring wants to prompt for a new login keyring password, and no prompter exists. keyring turns this into `InitError`.
- `keyring_usable()` (`src/fc_manager/credentials.py`) checks only the backend class name against a deny list. So `first_run()` (`cli/menu.py`) and `_precheck()` (`cli/profile.py`) pass, and `store()` fails after the prompts.

## Goals / Non-Goals

**Goals:**
- Find a broken keyring before the key prompt, with one read and no write.
- Say the cause in plain words, and give the fix.

**Non-Goals:**
- No file store, no encrypted file store (`keyrings.cryptfile`), no change to the "keyring only" rule.
- `fcm` does not start, create or unlock a keyring itself.
- The installed `fcm` does not read the `.env` file of `bin/fcm-dev`.

## Decisions

### D1: The probe is a read of a fixed, non-secret entry

`keyring_usable()` keeps the class-name test first. If the class passes, it calls `keyring.get_password(SERVICE, "__fcm_probe__")`. Any exception means "not usable". `None` or a value means "usable". The probe never writes.

- Why a read: on Secret Service, a read already opens the default collection, which is the step that fails here. A read leaves no entry behind.
- Alternative: write and delete a probe entry. Rejected: it writes to the user keyring, and a crash between the two steps leaves an entry.
- Alternative: call `secretstorage` directly. Rejected: it is Linux-only, and the probe must work the same way for every backend.
- The probe catches `Exception`, not only `KeyringError`. Some backends leak a D-Bus or OS error. Any failure means the keyring cannot hold the secret.

### D2: One probe per process

`_precheck()` runs two times in `fcm profile-add` (in `add()` and in `add_profile()`). The probe result is kept for the rest of the process, so a desktop unlock prompt shows only once. Tests reset the kept result with a fixture.

### D3: Callers do not change

`first_run()`, `_precheck()` and `_require_keyring()` already call `keyring_usable()` and raise the "no keyring" error. They keep that call. The only change in them is the message and the hint, which now come from one helper. The failure happens before the `try` block in `first_run()`, so the "Run fcm again to retry the setup" hint does not apply. That is correct, because a retry does not help.

### D4: One helper maps an exception to a plain cause

A helper turns the probe exception (or the exception of `store`, `load`, `delete`) into one sentence:

| Exception | Cause text |
| --- | --- |
| `InitError` | cannot open its default keyring (no login keyring, and no way to prompt for one) |
| `KeyringLocked` | is locked |
| `NoKeyringError` | has no backend |
| other | does not work (`<class name>`) |

Message: `The OS keyring on this host <cause>`. Hint: `ENV_HINT`, plus on Linux `See the README: "Keyring on a headless Linux host".` The text never holds a key or a secret. The class name stays in the message for `other`, so a bug report still shows it.

### D5: README is the place for the keyring fix

The fix for a headless host depends on the desktop stack (gnome-keyring, KWallet, none). The README gives the env-variable path first, then the gnome-keyring steps. The CLI hint only points to the README section.

## Risks / Trade-offs

- [The probe read shows an unlock prompt on a desktop with a locked login keyring, before the key prompt] → This is the correct order: the user unlocks first, and then types the key. D2 keeps it to one prompt.
- [A backend returns an error on a read of a missing entry, but writes work] → No such backend is known in keyring 25. If a report shows one, the deny list or the probe can treat that error as "usable".
- [The probe adds one D-Bus round trip to `fcm profile-add` and the first run] → Small, and only on those two paths. Commands that use a stored profile already read the keyring.

## Migration Plan

Patch release 1.1.1. No config or keyring data changes. Users run `uv tool install --force` (or the install command in the README) to update. Rollback: install 1.1.0.

## Open Questions

- The exact gnome-keyring commands for the README (for example `gnome-keyring-daemon --unlock` with the password on stdin) need a check on this host before the text is final. This changes the README only.
