# Tasks

## 1. FC migrate contract check

- [x] 1.1 Add `press.api.site.running_jobs` and `press.api.site.job` to `READ_ONLY_METHODS` (design D6). `press.api.site.jobs` and `press.api.client.get_list` are not on the list: both gave HTTP 500 over GET in the spike runs. Verify with `respx` tests that the 2 reads send a GET with the plain name, and that the client refuses both job list reads with no request.
- [x] 1.2 Extend `scripts/fc_spike.py` with a read-only site job section: `site.running_jobs` for one site, and `site.job` for a running job when one exists. The spike sends no write request. Also add `deploy_candidate`, `site` and `id` to the anonymizer fields, and keep the job type readable in `running_jobs` rows. Verify that the fixtures `site_running_jobs.json` and `site_job.json` hold no real name, id, secret or email, and match or correct design Context. The maintainer runs the spike with their own key, without `--write`. Done 2026-11-09 in 2 runs: `site.jobs` and then `client.get_list` gave HTTP 500 `AttributeError`, so the find step uses `running_jobs` (design D3). `running_jobs` gave HTTP 200 with an empty list. Both fixtures stay synthetic (no job was running); task 7.2 checks `site.job` and its step names.

## 2. API client write path

- [x] 2.1 Add `press.api.site.migrate` to `WRITE_METHODS`, and build the "result not known" hint and message from a per-method map (design D5). Verify with `respx` tests that a 502 or a timeout on the migrate sends exactly 1 request and raises `WriteUnknown` with "migrate" and `Run: fcm site-show <site>`, and that the deploy hint stays `Run: fcm bench-show <bench>`.

## 3. Migrate service

- [x] 3.1 Implement `migrate.py` dataclasses and parsers (`MigratePlan`, `MigrateState`, job steps) from the task 1.2 fixtures. Verify with unit tests on the real fixture shapes, on rows with missing fields, and on the "Undelivered" status read as "Pending".
- [x] 3.2 Implement `MigrateService.check()` (design D3). Verify with `respx` tests: Active, Inactive and Broken pass; Suspended, Pending and Archived raise exit 2 with the status in the message; a Running or Pending job from `running_jobs` raises exit 2 with the job type; the plan holds the site, the status and the skip flag.
- [x] 3.3 Implement `start()` and `watch()` with an injected sleep and clock. Verify with `respx` tests: `start()` sends 1 POST with `name` and `skip_failing_patches`; `watch()` waits for a "Migrate Site" job in `running_jobs` and ignores other job types, yields a state after every poll, ends on Success and on Failure with the failed step, reads the final site status once, and raises exit 6 with the site status when no migrate job appears within `FIND_LIMIT_SECONDS` (patched to 0).

## 4. Generic watch screen

- [x] 4.1 Move `_WatchView` to `cli/watch.py` behind the state protocol of design D4, and make `DeployState` and `MigrateState` give it. Verify that every existing deploy watch test passes with no change to its expected text, and that a new test shows the migrate status line with "last FC answer N s ago (poll N)" and "no answer from FC for N s".

## 5. CLI command

- [x] 5.1 Implement `migrate_site()` and the `site-migrate` command in `cli/migrate.py` (design D7), with `--skip-failing-patches`, `--confirm`, `--dry-run`, `--no-wait`, `--team`, `--json`, `--debug`, `--profile`. Add `migrate` to `WRITE_VERBS`. Verify with CLI tests: the preview content with and without the skip warning; a correct typed name sends 1 POST; a wrong name or an empty line sends none and exits 2; a script with no `--confirm` or a wrong one exits 2 with no POST; `--dry-run` sends no POST and exits 0; `--no-wait` exits 0 after the POST; success exits 0; failure exits 8; job not found exits 6; Ctrl+C in the watch exits 130 and says the migrate continues on FC.
- [x] 5.2 Implement the no-SITE walk: team, bench, then a site of that bench, with the path line on each prompt; exit 2 with no request in a script. Verify with fake-picker tests for both cases.
- [x] 5.3 Add `site-migrate` to the integration lists: the canary leak commands (as a dry run), the allowlist walk (a dry run and a real `--confirm ... --no-wait` run), and `sends_a_deploy` renamed to a check that each write command sends only its own method. Verify that the suite passes and that the walk fails when `site-migrate` sends the deploy method.
- [x] 5.4 Update `README.md`: the `site-migrate` command with an example, the menu entry, and exit code 8 for a failed migrate. Verify that `tests/test_cli_names.py` passes and that each documented command runs as written against the test fixtures.

## 6. Generic menu

- [x] 6.1 Replace `ACTIONS` and the `if`/`else` in `cli/menu.py` with the `Action` registry (design D1), with the entries Show bench, Deploy app updates, Migrate a site, Pick another bench, Quit. Verify that the existing menu tests pass and that each entry label names its direct command.
- [x] 6.2 Add the site step for site actions (design D2): sites of the picked bench only, with name and status; Esc goes back to the action menu; a bench with no site gives a message and the action menu; the path shows the site after the pick; after the action, the action menu of the same bench opens with no site in the path. Verify with menu tests for each of these, plus a migrate from the menu that sends no POST before the typed site name, and a Ctrl+C in the migrate watch that returns to the action menu.

## 7. Live check

- [x] 7.1 Live check through the picker, no write: the maintainer runs `bin/fcm-dev` with no command and walks team, bench, "Migrate a site", and a real staging site. At the confirmation, the maintainer types a wrong name, so nothing is sent. Verify the preview (target, site status, patch mode) by eye against the FC dashboard. Done when the maintainer accepts the preview. Done 2026-11-09: accepted by the maintainer.
- [x] 7.2 First real migrate through the picker: the same menu walk on a non-production site, and the maintainer types the site name. Verify that the watch finds the new job, follows its steps to the end, and that the result and the final site status match the FC dashboard. Then the action menu of the same bench opens again. Record the result in this task. Done 2026-11-09: the maintainer ran the menu walk and a real migrate on a non-production site, and reported that the tool works and the migrate works. The real step names were not recorded, so `site_job.json` stays synthetic.

## Workflow follow-up

- Commit the change on the maintainer's request.
- Archive the change with `/opsx:archive` after the live check, and run `./bin/openspec validate --specs --strict`.
- Update the `cli-hub-direction` memory: `site-migrate` done, next is `site-update`.
