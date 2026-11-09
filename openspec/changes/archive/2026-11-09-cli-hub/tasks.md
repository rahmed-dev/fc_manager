# Tasks

## 1. Hyphen command names

- [x] 1.1 Add `cli/root.py` with the root Typer `app` and `FcmGroup` (design D1). Move the root setup out of `cli/app.py`; `app.py` keeps `run()` and imports the command modules for registration. Verify that `fcm --help` still runs and that the test suite still collects.
- [x] 1.2 Register every command on the root app with its hyphenated name and its noun help panel: `profile-add`, `profile-list`, `profile-test`, `profile-remove`, `team-list`, `bench-list`, `bench-show`, `bench-deploy`, `site-list`, `site-show`. Remove the 4 sub-groups. Verify with a CLI test that `fcm --help` lists exactly these 10 commands in the groups Profile, Team, Bench, and Site.
- [x] 1.3 Add the old-form and bare-noun errors to `FcmGroup.resolve_command` (design D2), and change the plural hint to the `-list` command. Verify with CLI tests: `fcm bench list --team acme` exits 2 with "fcm bench-list" and sends no request; `fcm sites` exits 2 with "fcm site-list"; `fcm bench` exits 2 and lists `bench-list`, `bench-show`, and `bench-deploy`.
- [x] 1.4 Change every hint, message, and docstring that names a command to the new name (for example "Run: fcm bench-show <bench>"). Verify with a test that greps `src/` for the regex `fcm (profile|team|bench|site) (list|show|add|remove|test|deploy)` and finds no match.
- [x] 1.5 Update all tests to the new names, including the integration command lists, the canary leak suite, and the strict allowlist walk test (`READ_VERBS | WRITE_VERBS` now checks the verb part of each hyphenated name). Verify that the full suite passes.

## 2. Work functions for show and deploy

- [x] 2.1 Split `bench-show` into the command and `show_bench(s, bench)` (design D4). Verify that the existing `bench show` tests pass without a change in output.
- [x] 2.2 Split `bench-deploy` into the command and `deploy_bench(s, bench, options, *, in_menu)`. With `in_menu=True`: Esc at the app step raises `picker.GoBack` to the caller, and Ctrl+C in the watch raises `WatchStopped` in place of `typer.Exit(130)` (design D5). Verify that the existing deploy tests pass unchanged, and add tests for both `in_menu=True` signals.
- [x] 2.3 Add the optional `path` argument to `picker.choose` and `picker.choose_many`, and pass it from `deploy_bench` when `in_menu=True` (design D6). Verify with a picker test that the path line prints above the question, and that the direct command prints no path line.

## 3. Interactive menu

- [x] 3.1 Add the root callback with `invoke_without_command=True` and `--profile` (design D3). Not interactive: print the help and exit 0. Verify with a CLI test that `fcm` with no terminal prints the help, shows no prompt, and exits 0.
- [x] 3.2 Implement `cli/menu.py`: the team step (skipped with one team), the bench step for the picked team only, and the action menu with "Show bench (bench-show)", "Deploy app updates (bench-deploy)", "Pick another bench", and "Quit". Every prompt shows the target path. Verify with scripted-picker tests that the team pick lists only that team's benches, that the action menu prompt shows `profile > team > bench (name)`, and that "Quit" exits 0.
- [x] 3.3 Implement the return rules (design D5): after an action, after an `FcmError` (printed with its hint), after a cancelled confirmation, and after `WatchStopped`, the action menu of the same bench opens again. Verify with tests: a wrong typed title sends no POST and returns to the action menu; a show that raises a permission error prints the error and returns to the action menu.
- [x] 3.4 Implement Esc and Ctrl+C in the menu: Esc at the action menu goes to the bench step, Esc at the bench step goes to the team step, Esc at the team step exits 0, and Ctrl+C at a menu prompt exits 130 with no FC request. Verify each with a scripted-picker test.
- [x] 3.5 Verify with the strict allowlist walk test that a menu walk to "Deploy app updates" with a wrong title sends GET requests only, and that every request after the bench pick carries the team header of the picked team only.

## 4. Docs and live check

- [x] 4.1 Update `README.md`: the command grammar, every example, the new menu section, and the exit codes table if a row names a command. Update the module docstring of `cli/app.py` (the grammar line). Verify with the grep of task 1.4 over `README.md`.
- [x] 4.2 Read-only live check through `bin/fcm-dev` on a terminal: `fcm` opens the team picker; a team pick lists that team's benches; "Show bench" prints the bench and returns to the action menu; "Deploy app updates" with `--dry-run` is not in the menu, so stop at the confirmation and type a wrong title to check that nothing is sent and the action menu returns; Esc walks back to the team step and out. Record the result in this file. Done 2026-11-09 (driven in a pseudo-terminal on the real FC account, read-only): `fcm` opened the team picker with 13 teams; the bench step listed the picked team only; "Show bench" printed the bench and the action menu opened again; "Deploy app updates" showed the app and site steps with the target path line, the preview said "Bench only", a wrong typed title printed "Cancelled. Nothing was sent to FC." and the action menu opened again; Esc went action menu, bench, team, out, with exit code 0. The maintainer still has to accept this check.

## Workflow follow-up

- Run `/opsx:archive cli-hub` after the maintainer accepts the live check.
- Next changes, one per write action: `site-migrate`, then `site-update`, then add app. Each starts with a read-only spike for its FC method.
