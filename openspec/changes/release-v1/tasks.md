# Tasks

## 1. First-run setup

- [x] 1.1 Move the body of `profile-add` to `add_profile()` (design D2). Verify that every existing profile test passes with no change.
- [x] 1.2 Add the first-run check and the setup step to `menu.root` (design D1, D2). Verify with tests: no profile and no env credentials on a terminal runs the setup (name default `default`, key, secret), saves the profile as the default, and opens the menu; FC rejects the key: nothing stored, exit 3; no keyring: no prompt, exit 2 with the env hint; env credentials set: no setup; not a terminal: help, no prompt; a profile exists: no setup.

## 2. Version

- [x] 2.1 Add `fcm --version` (design D3) and set the version to 1.0.0. Verify with a test: output `fcm 1.0.0`, exit 0, no FC request and no credential read.

## 3. Packaging and docs

- [x] 3.1 Add `LICENSE` (MIT, 2026, rahmed-dev) and the `pyproject.toml` metadata (design D6). Verify that `uv build` passes and that the wheel METADATA has `License-Expression: MIT`.
- [x] 3.2 Add `scripts/check_wheel.py` and the CI step (design D4). Verify with a unit test on a synthetic wheel, and run the script on a real local build.
- [x] 3.3 Add `CHANGELOG.md` (1.0.0: the commands, the menu, the guards). Update `README.md`: install with `uv tool install git+https://github.com/rahmed-dev/fc_manager@v1.0.0` and `pipx`, the first run, upgrade, uninstall, and the dev clone path. Verify that `tests/test_cli_names.py`, `ruff check` and `./bin/openspec validate release-v1 --strict` pass.

## 4. Live check

- [x] 4.1 Add `bin/fcm-first-run` (design D5). The maintainer runs it, enters profile `first-run-check` and a real key, and sees the welcome, the FC user line and the menu. The maintainer quits; the helper removes the test profile. Done when the maintainer accepts the flow. Result on 2026-11-09: the first 2 runs took a wrong paste and showed the rejected path (nothing saved, the retry hint); this led to the key format check and the visible secret prompt (D7). The third run passed.

## Workflow follow-up

- Commit on the maintainer's request, archive with `/opsx:archive`, and run `./bin/openspec validate --specs --strict`.
- Then the publish steps, each with the maintainer's approval: backup bundle, history rewrite (remove the real id, author email to the GitHub noreply address), `master` to `main`, create the repo, push, tag `v1.0.0`, GitHub release, global install check.
