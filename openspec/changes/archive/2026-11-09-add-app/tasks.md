# Tasks

## 1. FC app contract check

- [x] 1.1 Add `press.api.bench.all_apps` and `press.api.site.available_apps` to `READ_ONLY_METHODS` (design D3). Verify with `respx` tests that each sends a GET with the plain name and no POST.
- [x] 1.2 Extend `scripts/fc_spike.py` with question 6 (design D10): read `all_apps` for the first bench of the first team and `available_apps` for the first Active site. Slim the rows, replace private app names, and cover the repository fields in the anonymizer. The spike sends no write request. Claude runs the read-only spike without `--write`, compares the shapes with the press source in design Context, and records the result in this task. Then add the fixtures `bench_all_apps.json`, `site_available_apps.json` and a synthetic `site_job_install.json`, and note them in the fixtures README. Verify that no fixture holds a real name, id, hash, secret or email. Result of the spike run on 2026-11-09: `all_apps` returns 388 rows (151 kB) with the keys of the press source, and 191 rows have a source for the group version; `available_apps` returns rows with the keys of the press source, and no row had plans. Both fixtures are real and anonymized. The plan rows are built in the tests, and the install job fixture stays synthetic until task 8.1.

## 2. API client write path

- [x] 2.1 Add `press.api.bench.add_app` and `press.api.site.install_app` to `WRITE_METHODS`, and to `WRITE_FOLLOW_UP` as `("add-app", "bench-show")` and `("install", "site-show")` (design D7). Verify with `respx` tests that a 502 or a timeout on each sends exactly 1 request and raises `WriteUnknown` with the right command hint.

## 3. Service

- [x] 3.1 Move the job loop of `MigrateService.watch()` into `watch_site_job()` (design D4). Verify that every migrate test passes with no change.
- [x] 3.2 Add `InstallFailed` (exit 8, with `step`) and `InstallUnknown` (exit 6) to `errors.py`. Implement the `apps.py` dataclasses and parsers from the task 1.2 fixtures (design D3). Verify with unit tests: the fixture shapes; rows with missing fields; the title fallback; an app with empty `sources` is not compatible; `has_plans_available` marks an app as not pickable.
- [x] 3.3 Implement `offered_apps()`, `pick_app()`, `pick_source()` and `add()`. Verify with `respx` tests: an unknown or not compatible `--app` raises exit 2 with the app name; one source is used with no prompt; several sources with no `--source` in a script raise exit 2 and list the branches; `add()` sends 1 POST with `name`, `source` and `app`.
- [x] 3.4 Implement `offered_site_apps()`, `check_site()`, `install()` and `watch_install()` (design D4, D5, D6). Verify with `respx` tests: only Active passes; Inactive, Broken and Pending raise exit 2 with the status; a running job raises exit 2 with the job type; an app with plans raises exit 2 and names the FC dashboard; `install()` sends 1 POST with `name` and `app` and no `plan`; the watch finds the `Install App on Site` job, ends on Success, raises `InstallFailed` on Failure with the step, and raises `InstallUnknown` when no job shows up past the limit (patched to 0).

## 4. CLI commands

- [x] 4.1 Implement `add_app_to_bench()` and `bench-add-app` in `cli/apps.py` (design D1, D8). Add `add-app` to `WRITE_VERBS`. Verify with CLI tests: the app step marks not compatible apps; the source step; the preview content (bench, version, app, branch, repository, deploy note); nothing to add exits 0 with no POST; a correct typed bench title sends 1 POST; a wrong title or an empty line sends none and exits 2; a script with no `--confirm`, a wrong one, or no `--app` exits 2 with no POST; `--dry-run` sends no POST and exits 0; success exits 0 and names `fcm bench-deploy <bench>`; no BENCH in a script exits 2 with no request.
- [x] 4.2 Implement `install_app_on_site()` and `site-install-app` (design D8). Add `install-app` to `WRITE_VERBS`. Verify with CLI tests: the checks; the app step with plans shown as not pickable; the preview content; nothing to install exits 0; a correct typed site name sends 1 POST; a wrong name sends none and exits 2; a script with no `--confirm` or no `--app` exits 2 with no POST; `--dry-run` sends no POST; `--no-wait` exits 0 after the POST; success exits 0; Failure exits 8 with the step; job not found exits 6; Ctrl+C in the watch exits 130 and says the install continues on FC; the no-SITE walk in a terminal and in a script.
- [x] 4.3 Update `test_cli_core.py` with the 2 new names, and add both commands to the integration lists: the canary leak commands (as a dry run), the allowlist walk (a dry run and a real `--confirm` run), `OWN_WRITE`, and the wrong-write guard. Add the FakeFC handlers for `all_apps`, `available_apps`, `add_app` and `install_app`. Verify that the suite passes, and that the walk fails when a command sends another write method.
- [x] 4.4 Update `README.md`: both commands with examples, the 2 menu entries and "Deploy now?", exit codes 6 and 8 for the install, the plan rule, and the allowlist text. Update `CHANGELOG.md` with an Unreleased entry. Verify that `tests/test_cli_names.py` passes and that the help lists the new commands in the Bench and Site groups.

## 5. Menu

- [x] 5.1 Add `picker.ask_yes_no()` and the 2 `Action` entries, with the "Deploy now?" step after an add (design D9). Verify with menu tests: the entry order; an add from the menu sends no POST before the typed bench title; a yes to "Deploy now?" starts the deploy walk at the app step; a no or Esc shows the action menu; an install from the menu sends no POST before the typed site name; a Ctrl+C in the install watch returns to the action menu.

## 6. Checks

- [x] 6.1 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and `./bin/openspec validate add-app --strict`. Verify that all pass.

## 9. Rework of the add step (after the first menu check, 2026-11-09)

- [x] 9.1 Spike question 7 (GitHub reads) and the allowlist entries for `github.options`, `github.branches` and `github.app`. Result of the spike run on 2026-11-09: all 3 reads return HTTP 200 with the shapes in design Context. Add synthetic fixtures `github_options.json` and `github_branches.json`, and the real public `github_app.json`.
- [x] 9.2 Write path: replace `press.api.bench.add_app` with `press.api.bench.add_apps`, and add `press.api.client.run_doc_method` with `WRITE_DOC_METHODS` (design D12). Verify with `respx` tests: one POST each; `run_doc_method` for another doctype or method raises with no request; a 502 names `fcm bench-show <bench>`.
- [x] 9.3 `SearchIndex` and the app cache (design D11). Verify with unit tests: the rank order (exact, prefix, word prefix, inside, letters in order); at most 10 rows; not compatible apps never match; an empty query gives no rows; a second `offered_apps()` for the same bench sends no request; a search over the 388-row size (fixture rows repeated) runs in under 5 ms per query.
- [x] 9.4 GitHub service: repositories, URL parse, branches order, app read, the "bench already has it" check, and the `run_doc_method` body (design D12). Verify with `respx` tests.
- [x] 9.5 CLI and menu: the source choice, `picker.search()`, "Add another app?", the GitHub steps, and the options `--app` (repeat), `--source app=source`, `--repo`, `--branch`. Verify with CLI and menu tests, and update the integration lists, the README and the CHANGELOG.
- [x] 9.6 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` and `./bin/openspec validate add-app --strict`.

## 7. Live check, no write

- [x] 7.1 The maintainer runs `bin/fcm-dev` with no command and walks team, bench, "Add an app". The maintainer tries both sources: a marketplace search (type a few letters, check the 10 matches, pick 2 apps) and a GitHub repository and branch. For each, the maintainer reads the preview and types a wrong title, so nothing is sent. First result on 2026-11-09: the app step printed all 388 apps with no search, and there was no GitHub source; this led to group 9. Second result on 2026-11-09, after group 9: the maintainer accepted the marketplace search, the GitHub steps and the previews. Then the same for "Install an app" on a real site. Verify by eye against the FC dashboard: the app lists, the not compatible and plan marks, and the previews. Done when the maintainer accepts both previews.

## 8. First real writes

Open at release v1.1.0 (decision by Riz, 2026-11-09: release before the real writes). The CHANGELOG names this gap.

- [ ] 8.1 First real install through the menu on a non-production site, with a free app that is already on the bench. Verify that the watch follows the job to the end, and that the result matches the FC dashboard. Record the real step titles here, and correct `site_job_install.json` if they differ.
- [ ] 8.2 First real add through the menu, on a non-production bench. Verify on the FC dashboard that the group has the app. Answer yes to "Deploy now?" and verify that the new app is in the deploy app step. The maintainer decides at the deploy confirmation whether to deploy or to type a wrong title.

## Workflow follow-up

- Commit the change on the maintainer's request.
- Archive the change with `/opsx:archive` after the live checks, and run `./bin/openspec validate --specs --strict`.
- Update the `cli-hub-direction` memory: add app done.
