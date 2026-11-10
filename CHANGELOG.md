# Changelog

All notable changes to `fcm` are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow
[Semantic Versioning](https://semver.org/).

## [1.2.1] - 2026-11-10

### Changed

- The app list of `bench-deploy` shows the branch of each app in brackets, for example
  `[version-15]`, or `[main -> version-15]` when the deploy changes the branch. The names,
  the branches and the versions line up in columns.

## [1.2.0] - 2026-11-10

### Changed

- The first run and `profile-add` ask for the key again on a host where no keyring works
  (1.1.1 stopped before the prompts). After FC accepts the key, `fcm` says why the keyring
  does not work and asks to save the key in `~/.config/fc_manager/credentials` (mode 0600).
  The default answer is No: then nothing is saved.
- `profile-list` shows the store of each profile (`keyring` or `file`). `profile-remove`
  and `profile-add --replace` handle both stores.

### Removed

- The gnome-keyring steps in the README. They did not work on a headless host.

## [1.1.1] - 2026-11-10

### Fixed

- First run and `profile-add` on a host where a keyring service runs but cannot open a
  keyring (for example gnome-keyring on a headless server with no login keyring): `fcm` now
  tests the keyring with one read before it asks for the key. It asks for nothing, says why
  the keyring does not work, and names `FCM_API_KEY` and `FCM_API_SECRET`. Before, it asked
  for the key and then failed with `Cannot write to the OS keyring: InitError`.
- Keyring errors say the cause in plain words (no default keyring, locked, no backend), not
  only an exception name.

## [1.1.0] - 2026-11-09

### Added

- `bench-add-app`: add apps to a bench group, with a preview and a typed bench title.
  From the marketplace: a local ranked search (at most 10 matches) and several apps in one
  request. From GitHub: a repository of the team's installations or a public URL, then a
  branch; one app per run. The apps reach the benches at the next deploy. In the menu,
  "Add an app" then asks "Deploy now?".
- `site-install-app`: install an app of the bench on one site, with a preview, a typed site
  name, and a live watch of the install job. Apps with marketplace plans are refused: install
  them from the FC dashboard.
- Search prompts: the marketplace and branch steps show at most 10 ranked matches as you
  type. The search runs locally and sends nothing to FC.

### Known gaps

- The first real install and the first real add through the menu are not checked yet. The
  step names of the FC install job come from the press source and are not confirmed.

## [1.0.0] - 2026-11-09

First public release.

### Added

- Profiles: `profile-add`, `profile-list`, `profile-test`, `profile-remove`. Secrets live
  in the OS keyring only. `FCM_API_KEY` and `FCM_API_SECRET` work as a fallback.
- First-run setup: `fcm` with no profile asks for the API key and secret, checks them with
  FC, and opens the menu.
- Read commands over every team of a login: `team-list`, `bench-list`, `bench-show`,
  `site-list`, `site-show`, with `--json` output.
- `bench-deploy`: deploy app updates to a bench, with a preview, a typed bench title, and a
  live watch of the build. Sites are optional and none is selected by default.
- `site-migrate`: run a migrate on one site, with a preview, a typed site name, and a live
  watch.
- `site-update`: move one site to the newest bench of its bench group, with a preview of the
  app versions, a typed site name, and a live watch.
- The menu: `fcm` with no command walks team, bench, then an action, and returns to the
  action menu after each action.
- `fcm --version`.

### Security

- Only allowlisted FC methods are called. Writes are POST only and never retried.
- Every write needs a typed confirmation, or `--confirm` with the exact target in a
  script. There is no `--yes` for a write.
- Secrets are redacted from all output, including `--debug`.

[1.0.0]: https://github.com/rahmed-dev/fc_manager/releases/tag/v1.0.0
