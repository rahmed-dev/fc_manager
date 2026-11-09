# Changelog

All notable changes to `fcm` are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the versions follow
[Semantic Versioning](https://semver.org/).

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
