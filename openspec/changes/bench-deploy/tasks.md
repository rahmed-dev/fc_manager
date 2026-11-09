# Tasks

## 1. FC deploy contract check

- [x] 1.1 Extend `scripts/fc_spike.py` with a read-only deploy section: `bench.deploy_information` for one bench, `bench.deploy_status` for the same bench, and the Deploy Candidate Build of its `last_deploy` through `press.api.client.get` (when one exists). Add these methods to the read allowlist first, with `client.get` limited to the doctype `Deploy Candidate Build`. The spike sends no write request. Verify that the anonymized fixtures `bench_deploy_information.json`, `bench_deploy_status.json`, and `deploy_candidate_build.json` exist under `tests/fixtures/fc/`, contain no secret or personal data, and match or correct the field list in design Context. Record any difference in design Risks before task 3.

## 2. API client write path

- [x] 2.1 Add the deploy read methods to `READ_ONLY_METHODS` (with the `client.get` doctype check), and add `WRITE_METHODS` with `press.api.bench.deploy_and_update` only (design D1). Make `call()` reject a write method. Verify with `respx` tests that `call("press.api.bench.deploy_and_update")` raises and sends no request.
- [x] 2.2 Implement `FCClient.write()`: POST, JSON body, team header, write allowlist only, no retry, and a `WriteUnknown` error on a timeout or 5xx. Verify with `respx` tests that a 502 or a timeout sends exactly 1 request and raises `WriteUnknown` with the `fcm bench show` hint, and that a read method through `write()` raises with no request.
- [x] 2.3 Add `DeployFailed` (exit 8) and `WriteUnknown` (exit 6) to `errors.py`. Verify with the exit-code unit test that `JOB_FAILED` maps to 8.
- [x] 2.4 Extend the canary leak suite and the strict allowlist walk test to the new commands and the write path. Verify that the canary never appears in output for deploy errors, and that the walk test fails when any command other than `bench deploy` sends a POST.

## 3. Deploy service

- [x] 3.1 Implement `deploy.py` dataclasses and parsers for `DeployInfo` (apps, removed apps, sites, flags) and `DeployState` (stage, candidate, build steps) from the task 1.1 fixtures. Verify with unit tests on the real fixture shapes and on rows with missing fields.
- [x] 3.2 Implement `DeployService.plan()`: validate app and site names, take each release from `releases[]` where `name == next_release` and not yanked, and build the exact FC payload. Verify with unit tests: default selections, an unknown app, an unknown site, a yanked next release, a bench-only plan (empty site list), and a plan with only removed apps.
- [x] 3.3 Implement `info()`, `start()`, `state()`, and `watch()` (design D2, D6) with an injected sleep. Verify with `respx` tests: every request carries the bench team, `start()` sends 1 POST with the plan payload, `watch()` polls no faster than 2 s, and it ends on success, on failure (with the failed step), and on both the pipeline-name and the candidate-name return of `start()`.

## 4. Picker multi-select

- [x] 4.1 Add `picker.choose_many(prompt, options, default_selected)` with search, Esc to go back, and Ctrl+C to cancel with exit 2. Verify with tests that patch `questionary`: apps open all selected, sites open none selected, and a cancel exits 2.

## 5. CLI commands

- [x] 5.1 Implement `fcm bench show [BENCH] [--team]` (design D8). Verify with CLI tests: apps with updates, sites, a running deploy with its build steps, `--json` shape, and no POST sent.
- [x] 5.2 Implement the `fcm bench deploy` walk: bench resolve or picker, scoped `info()`, nothing-to-deploy (exit 0), deploy-in-progress (exit 2), app step, site step always shown, Esc back. Verify with CLI tests that after the bench pick every request carries only that bench team.
- [x] 5.3 Implement the preview from `DeployPlan` and the typed confirmation (title on a terminal, `--confirm <name>` in scripts, no `--yes`), plus `--dry-run`. Verify with CLI tests: the preview fields, an exact title starts the deploy, a wrong or empty input sends no POST and exits 2, `--confirm` missing or wrong exits 2 with no POST, and `--dry-run` exits 0 with no POST.
- [x] 5.4 Implement the non-interactive options `--app`, `--all-apps`, `--site`, and `--no-wait`. Verify with CLI tests: no app option exits 2, an unknown site exits 2 and lists the bench sites, no `--site` gives a bench-only payload, and `--no-wait` returns after the POST.
- [x] 5.5 Implement the progress view (rich `Live` on a terminal, JSON lines otherwise), the result, Ctrl+C during the watch, and the error mapping (validation exit 1, failed build exit 8, permission hint with the team owner). Verify with CLI tests for each end state, and that Ctrl+C sends no further request and prints the `fcm bench show` hint.

- [x] 5.8 Watch liveness (added 2026-11-09 after the maintainer saw a frozen screen during the first real deploy): the service yields one state per FC answer; the terminal view shows the time since the last FC answer, the poll count, the elapsed time, the running-step time, and a warning after 10 s with no answer. JSON and plain output print changes only.
- [x] 5.9 Site update wait (added 2026-11-09 after the first real deploy gave a false "site did not move", exit 8): FC moves each selected site in a separate job after the new bench is ready, and no busy flag covers that job. The watch now has an `updating_sites` stage that polls until each site is on a new bench, shows each site as waiting or moved, and after 30 minutes exits 6 with "result not known". Build step times show a unit.

## 6. Docs and specs check

- [x] 6.1 Update the README: the `bench deploy` walk, the typed confirmation, bench-only deploy, `--dry-run`, `fcm bench show`, and exit code 8. Update the README security section: the write allowlist and no retry of a write. Verify by reading the README against the specs.
- [x] 6.2 Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `./bin/openspec validate bench-deploy --strict`. Verify that all pass.

## 7. Live check

- [x] 7.1 Read-only live check: `fcm bench show` and `fcm bench deploy --dry-run` on 2 real benches through `bin/fcm-dev`. Verify the preview by eye against the FC dashboard deploy dialog for the same bench. Done 2026-11-09: the maintainer compared the dry run on a real staging bench (1 app, 1 site) with the FC dashboard; it matches. The next version label now reads the version from the FC release message when the release has no tag.
- [x] 7.2 First real deploy: the maintainer picks a non-production bench with an available update and runs `fcm bench deploy` on a terminal with no site selected (bench only). Verify that the watch follows the build to the end, the result matches the FC dashboard, and no site moved. Record the result in the change notes. Done 2026-11-09: the maintainer deployed `frappe` v16.25.0 to v16.55.2 on a real staging bench through the interactive walk, with its one staging site selected (not bench only). FC accepted the deploy, and the maintainer accepted the result. A read-only `fcm bench show` after the deploy shows no deploy running and no update left for `frappe`. The frozen watch screen seen during this deploy led to task 5.8. The site moved after the bench was ready, which `fcm` first reported as "did not move"; that led to task 5.9.

## Workflow follow-up

- Run `./bin/openspec validate bench-deploy --strict` before archive.
- Archive the change with `/opsx:archive` after review.
- Later changes: `fcm site update <site>`, the team-first `site show` picker, a local deploy audit log, and the TUI.
