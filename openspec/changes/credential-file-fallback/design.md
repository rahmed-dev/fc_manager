# Design

## Context

See proposal.md - Why. Today (1.1.1) `_precheck()` (`cli/profile.py`) and `first_run()` (`cli/menu.py`) stop before the prompts when `credentials.keyring_usable()` is false. `credentials.load(name)` and `delete(name)` know only the keyring. `config.Profile` holds `name` and `base_url`.

## Goals / Non-Goals

**Goals:**
- One setup flow on every host: prompts, FC check, then the save.
- A file store with the same safety level as the config file (0600 in a 0700 directory) and an explicit yes.

**Non-Goals:**
- No encryption of the file. An encrypted file needs a password on each run, which is worse than the environment variables.
- No command to move a profile between stores. `--replace` does it.
- The file store is not offered when the keyring works.

## Decisions

### D1: The store is a field of the profile in config.toml

`Profile.store` is `"keyring"` (default) or `"file"`. `to_toml()` writes `store` only for `file`, so old and new keyring profiles look the same. `load()` refuses any other value.

- Alternative: look in the keyring first, then in the file. Rejected: each command would touch a broken keyring, and the order of lookups hides where the secret is.

### D2: Credentials file format and path

Path: `config_path().parent / "credentials"` (so `FCM_CONFIG_DIR` moves it too). TOML:

```toml
[profiles.default]
api_key = "..."
api_secret = "..."
```

Write: same atomic pattern as `config.save()` (temp file with `os.open(..., 0o600)`, `chmod 0600`, `os.replace`). The write keeps the entries of other profiles. Read: `stat` first; if `st_mode & 0o077` is not 0, refuse with the hint `chmod 600 <path>`. A missing file or entry gives the same error as a missing keyring entry (hint `fcm profile-add <name> --replace`).

### D3: The save step in `add_profile()`

Order: prompts, token check, FC check, then:

1. `keyring_problem()` is None: `store(name, creds)` to the keyring, `store = "keyring"`.
2. Else: print `No working OS keyring on this host: the OS keyring <cause>.`, then confirm `Save the key in <path> (mode 0600, only you can read it)?` with default No.
3. Yes: write the file, `store = "file"`. No: raise `KeyringDeclined` (a `UsageError`) with `keyring_hint()`.

`_precheck()` drops its keyring check. `first_run()` drops its keyring check. In `first_run()`, the "Run fcm again to retry the setup" hint replaces the hint of every error, except `KeyringDeclined`, which keeps the environment-variable hint.

### D4: Store-aware load and delete

`credentials.load(profile, store="keyring")` and `credentials.delete(profile, store="keyring")`. `resolve()`, `profile-test` and `profile-remove` pass `profile.store`. `--replace`: after the new save, if the old store differs, delete the old entry; a `UsageError` from a keyring delete is ignored (D3 of the spec: the save does not stop).

### D5: README

The section "Keyring on a headless Linux host" keeps its title, because the CLI hint names it. It now says: setup offers the file; the environment variables are the other option; how to move to the keyring later with `--replace`. The gnome-keyring steps go away.

## Risks / Trade-offs

- [The secret is plain text on disk] → Only after a yes, only with no keyring, mode 0600, and the README says so. The same model as the AWS CLI and `gh`.
- [A backup tool copies the file] → Stated in the README.
- [The user does not see the question in a scripted run] → `profile-add` and the setup already need a terminal.

## Migration Plan

Release 1.2.0. Old config files need no change. Rollback to 1.1.1: a file profile then fails with "No credentials in the keyring" and the hint to replace it; the credentials file stays on disk until the user deletes it.
