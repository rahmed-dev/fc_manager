# Tasks

## 1. FC update contract check

- [x] 1.1 Add `press.api.site.check_for_updates` to `READ_ONLY_METHODS` and `Site Update` to `READ_DOCTYPES` (design D1, D2). Verify with `respx` tests that `check_for_updates` sends a GET with the plain name, that `client.get` of `Site Update` sends a GET with the doctype and the name, and that a `client.get` of `Site` is still refused with no request.
- [x] 1.2 Extend `scripts/fc_spike.py` with question 5 (design D9): read `check_for_updates` for the first site with `update_available` in `site.all` (all teams), and add the hash fields of the app rows to the anonymizer and replace private app names. The spike sends no write request. Add the synthetic fixtures `site_check_for_updates.json` and `site_update.json` (from the press source in design Context), and note them in the fixtures README. Claude runs the read-only spike, without `--write`. Verify that no fixture holds a real name, id, hash, secret or email. Result of the spike run on 2026-11-09: in 13 teams, only 1 site has `update_available`, and FC gives HTTP 403 "Not Permitted" for `site.get`, `site.running_jobs` and `check_for_updates` on that site (the key has no permission on it; other sites read fine). So the real `check_for_updates` shape is not confirmed, and the fixture stays synthetic. Task 7.1 confirms the shape.

## 2. API client write path

- [x] 2.1 Add `press.api.site.update` to `WRITE_METHODS` and `WRITE_FOLLOW_UP` as `("update", "site-show")` (design D7). Verify with `respx` tests that a 502 or a timeout on the update sends exactly 1 request and raises `WriteUnknown` with "update" and `Run: fcm site-show <site>`.

## 3. Update service

- [x] 3.1 Add `UpdateFailed` (exit 8, with `step` and `outcome`) and `UpdateUnknown` (exit 6) to `errors.py`. Implement the `update.py` dataclasses and parsers (`UpdateInfo`, `AppChange`, `UpdatePlan`, `UpdateState`) from the task 1.2 fixtures (design D2). Verify with unit tests: the fixture shapes; rows with missing fields; the version is the tag, else the short hash; only apps with `update_available` are kept; a branch change is flagged; each record status maps to its stage, and only Success, Recovered, Fatal and Cancelled are final.
- [x] 3.2 Implement `UpdateService.info()` and `check()` (design D2, D3, D4). Verify with `respx` tests: no update gives `NothingToUpdate`; Active and Inactive pass; Broken, Suspended and Pending raise exit 2 with the status in the message; a Running or Pending job from `running_jobs` raises exit 2 with the job type; the plan holds the site, the status, the app changes and the skip flag.
- [x] 3.3 Implement `start()` and `watch()` with an injected sleep and clock (design D1). Verify with `respx` tests: `start()` sends 1 POST with `name`, `skip_failing_patches` and `skip_backups` false, and returns the record name; an answer with no string name raises `UpdateUnknown`; `watch()` yields a state after every poll; it ends on Success with the new bench; it keeps polling through Failure and Recovering; it raises `UpdateFailed` for Recovered, Fatal and Cancelled with the failed step; a Failure with no `recover_job` past the limit (patched to 0) raises `UpdateFailed`; it reads the final site status once.

## 4. Site step and walk

- [x] 4.1 Add the `only` filter and the `empty` message to `choose_site`, and move `_walk_to_site` to `cli/inventory.py` as `walk_to_site` (design D5, D6). Verify that every existing migrate and menu test passes with no change, and that a new test lists only the sites with `update_available` and prints the `empty` message when none is left.

## 5. CLI command

- [x] 5.1 Implement `update_site()` and the `site-update` command in `cli/update.py` (design D8), with `--skip-failing-patches`, `--confirm`, `--dry-run`, `--no-wait`, `--team`, `--json`, `--debug`, `--profile`, and no `--skip-backups`. Add `update` to `WRITE_VERBS`. Verify with CLI tests: the preview content (apps current to next, branch note, down-and-backup line, patch mode, skip warning); no update exits 0 with no POST; a correct typed name sends 1 POST; a wrong name or an empty line sends none and exits 2; a script with no `--confirm` or a wrong one exits 2 with no POST; `--dry-run` sends no POST and exits 0; `--no-wait` exits 0 after the POST; success exits 0; Recovered, Fatal and Cancelled exit 8 with their own text; a missing record name exits 6; Ctrl+C in the watch exits 130 and says the update continues on FC; `--skip-backups` is not an option.
- [x] 5.2 Implement the no-SITE walk with the update filter, and exit 2 with no request in a script. Verify with fake-picker tests for both cases, and that the site step lists only the sites with an update.
- [x] 5.3 Add `site-update` to the integration lists: the canary leak commands (as a dry run), the allowlist walk (a dry run and a real `--confirm ... --no-wait` run), `OWN_WRITE`, and the wrong-write guard. Add the FakeFC handlers for `check_for_updates`, `site.update` and `client.get` of `Site Update`. Verify that the suite passes and that the walk fails when `site-update` sends another write method.
- [x] 5.4 Update `README.md`: the `site-update` command with an example, the menu entry, exit codes 6 and 8 for the update, and the allowlist text. Verify that `tests/test_cli_names.py` passes and that the help lists `site-update` in the Site group.

## 6. Menu

- [x] 6.1 Add `site_filter` to `Action`, and add the entry "Update a site (site-update)" with the update filter after "Migrate a site" (design D5). Verify with menu tests: the entry order; the site step lists only the sites with an update; a bench with no such site gives "No site of bench X has an update." and the action menu; an update from the menu sends no POST before the typed site name; a Ctrl+C in the update watch returns to the action menu.

## 7. Live check

- [x] 7.1 Live check through the picker, no write: the maintainer runs `bin/fcm-dev` with no command and walks team, bench, "Update a site", and a real site with an update. At the confirmation, the maintainer types a wrong name, so nothing is sent. Verify the preview (target, site status, app versions, patch mode) by eye against the FC dashboard. This also checks the real `check_for_updates` shape: an app list that is empty or wrong in the preview means the shape differs from `site_check_for_updates.json`, and the fixture and the parser are corrected. Done when the maintainer accepts the preview. Result on 2026-11-09: the maintainer accepted the preview in the menu.
- [x] 7.2 First real update through the picker: the same menu walk on a non-production site, and the maintainer types the site name. Verify that the watch follows the update record to the end, and that the result, the new bench and the final site status match the FC dashboard. Then the action menu of the same bench opens again. Record the real step titles in this task, and correct `site_update.json` if they differ. Result on 2026-11-09: the maintainer ran a real update through the menu, and it succeeded. The maintainer reported no step title that differs from the fixture, so `site_update.json` stays as it is.

## Workflow follow-up

- Commit the change on the maintainer's request.
- Archive the change with `/opsx:archive` after the live check, and run `./bin/openspec validate --specs --strict`.
- Update the `cli-hub-direction` memory: `site-update` done, next is add app.
