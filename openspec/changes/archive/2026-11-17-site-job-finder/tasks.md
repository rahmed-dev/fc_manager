# Tasks

## 1. Live job fixtures (read-only spike)

- [x] 1.1 With `scripts/fc_spike.py`, read `press.api.site.running_jobs` and `press.api.site.job` (GET only, no write) for the "Update Site Migrate" (Failure) and "Recover Failed Site Update" jobs of the site in the 2026-11-17 failure. Save the redacted answers as `tests/fixtures/fc/site_job_update_failed.json` and `site_job_recover.json`. Verify: each file holds the job type, the status, and the steps with `step_name` and `output`.
- [x] 1.2 Record in `tests/fixtures/fc/README.md` which job type names the spike confirmed ("Update Site Migrate", "Recover Failed Site Update") and which stay unconfirmed ("Update Site Pull"). Verify: the README lists each name with its source.

## 2. Shared site job watch

- [x] 2.1 Create `src/fc_manager/jobs.py`. Move `JobRow`, `JobStep`, `parse_running_jobs`, `parse_job`, `IN_PROGRESS` and `JOB_DONE` out of `migrate.py` into it, and update the imports in `migrate.py`, `apps.py` and `update.py`. Verify: `uv run pytest` passes with no test change.
- [x] 2.2 Add `JobSpec` (expected types, find limit, recover flag) and `SiteJobWatch` to `jobs.py` (design D1, D2): find every new job in `running_jobs`, follow each with `site.job`, decide on the expected job only, end with success, failure or not known. Add `tests/test_jobs.py` with the fake clock. Verify: tests cover an expected job that succeeds, one that fails with its step and output, an unrelated job that fails without an end of the watch, and no job within the find limit.
- [x] 2.3 Add the recovery step to `SiteJobWatch` (design D3): a "Recover Failed Site ..." job result, or the site status Active, Inactive or Broken, decides "restored" or "not restored"; 10 minutes with neither gives "failed, no recovery". Verify: `test_jobs.py` covers a recover job in Success, a recover job in Failure, a missed recover job with the site Active, the site Broken, and the 10-minute limit.
- [x] 2.4 Write the module docstring of `jobs.py`: what the watch reads, the 2-second poll, and the short-job limit. Verify: `uv run ruff check` passes and the docstring names the short-job limit.

## 3. Migrate and install on the shared watch

- [x] 3.1 Replace `watch_site_job()` in `migrate.py` with `SiteJobWatch` for the "Migrate Site" type, and in `apps.py` for "Install App on Site". Map the results to `MigrateFailed` / `MigrateUnknown` and `InstallFailed` / the install unknown error as today. Verify: `tests/test_migrate.py`, `tests/test_apps.py`, `tests/test_cli_migrate.py` and `tests/test_cli_apps.py` pass with no change in the expected messages or exit codes.

## 4. Site update on the shared watch

- [x] 4.1 Change `UpdateService.start()` to return the record name or an empty string, and remove the `UpdateUnknown` raise for a missing name (design D6). Verify: a test in `tests/test_update.py` sends an answer with no name and gets an empty string, not an error.
- [x] 4.2 Change `UpdateService.watch()` to use `SiteJobWatch` with the types "Update Site Migrate" and "Update Site Pull" and the recover flag. Remove `parse_update_record`, the record `STAGES`, `RECORD_DOCTYPE`, the "cancelled" outcome, and the fixture `site_update.json`. Verify: `tests/test_update.py` covers success, failure restored by a recover job, failure with the site back to Active, failure with the site Broken, no recovery in 10 minutes, and no update job in 2 minutes, with the fixtures of task 1.1.
- [x] 4.3 Update `cli/update.py`: the stage texts for the new stages, the record name shown only when FC gives it, the failed job and step with the FC output, and no bench name on success. Verify: `tests/test_cli_update.py` passes, and the failure test output holds the job type, the step and the output text.
- [x] 4.4 Remove the doctype `Site Update` from `READ_DOCTYPES` in `api/client.py` (design D7). Verify: a test in `tests/test_client.py` asks `client.get` for `Site Update` and gets `MethodNotAllowed` with no request sent.

## 5. Bench deploy site results

- [x] 5.1 Replace the bench-change loop in `DeployService.watch()` with one `SiteJobWatch` for each selected site, stepped in one loop (design D4), with the 30-minute find limit. Replace the `(site, moved)` pairs in `DeployState` with site results. Verify: `tests/test_deploy.py` covers one site updated, one site failed at "Backup Site Tables" with the `Too many connections` output, one site not found in 30 minutes, and a deploy with no selected site that reads no site job.
- [x] 5.2 Raise the deploy result errors (design D5): `DeployFailed` (exit 8) when one or more sites failed, else `SiteUpdateUnknown` (exit 6) when one or more sites are not known. Verify: a `test_deploy.py` test with one site updated and one failed gets exit kind JOB_FAILED, and one with one updated and one not known gets SERVER.
- [x] 5.3 Update `cli/deploy.py`: one line for each site with its result, job, step and output; the `sites` list in `--json` with `site`, `result`, `job`, `step`, `output` and `outcome`. Verify: `tests/test_cli_deploy.py` checks the terminal text and the JSON for the failed-site case.

## 6. Integration and release

- [x] 6.1 Run `uv run pytest` and `uv run ruff check`. Verify: both pass with no skip that this change adds.
- [ ] 6.2 Ask Riz to run one `site-update` and one `bench-deploy` with a selected site through the `bin/fcm-dev` menu. Verify: Riz confirms the per-site result on screen, and any new job type name from the run goes into the fixtures README.
- [x] 6.3 Set the version to 1.3.0 in `pyproject.toml`, and add a CHANGELOG entry that names the exit code change (deploy with a failed site update: 6 to 8) and the removed "Cancelled" outcome. Verify: `fcm --version` prints 1.3.0.

## Workflow follow-up

- Archive the change with `/opsx:archive` after Riz approves the live run of task 6.2.
