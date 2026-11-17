# Proposal

## Why

`fcm bench-deploy` does not report a failed site update. After the new bench is ready, it only checks whether each selected site moved to a new bench. It never reads the FC jobs of the site. On 2026-11-17, the update of a selected site failed on FC after 40 s, in the job "Update Site Migrate" at the step "Backup Site Tables", with `mariadb-dump: Got error: 1040: "Too many connections" when trying to connect`. fcm waited 30 minutes and then said only that the result was not known.

fcm also has three ways to follow work on a site: `watch_site_job()` for migrate and install, the `Site Update` record watch for `site-update`, and the bench-change loop for `bench-deploy`. One shared site-job finder removes the extra code, and every action then reports a failure the same way, with the failed step and the FC error text.

## What Changes

- New shared site-job watch. It finds the FC jobs of a site after an action, through `press.api.site.running_jobs`. It follows each job to its end through `press.api.site.job`, and reports the failed step and its FC output. The data is the same as the Jobs tab of the FC dashboard.
- `bench-deploy`: after the new bench is ready, the watch follows the site update job of each selected site. The result shows one line for each site: updated, failed with the step and the FC error text, or not known. **BREAKING**: the result of a deploy with a failed site update changes from exit 6 ("not known") to exit 8 (job failed).
- `bench-deploy`: the "site is on a new bench" loop goes away. The 30-minute limit stays only for the case where no site update job of a site shows up.
- `site-update`: the watch follows the FC jobs of the site, not the `Site Update` record. The code that reads the record goes away. FC still returns the record name, and fcm still shows it, but fcm no longer needs it. **BREAKING**: a missing record name in the FC answer no longer ends the command with exit 6.
- `site-update`: the outcome after a failed update job (restored to the old bench, could not restore) comes from the recover job and the site status. The "Cancelled" outcome goes away, because FC jobs do not show it.
- `site-migrate` and `site-install-app`: no change in behavior. Their watch moves to the shared site-job watch.

## Capabilities

### New Capabilities
- `site-job-watch`: how fcm finds and follows the FC jobs of one site after an action, reports progress and liveness, and reports a failed job with its step and FC output.

### Modified Capabilities
- `bench-deploy`: "Site update wait" now follows the site update job of each selected site. "Deploy result" now reports a result for each selected site, including a failed site update with exit 8.
- `site-update`: "Update request", "Update watch", "Update result" and "Update failure outcome" now use the site jobs, not the `Site Update` record.
- `fc-api-access`: "Site update reads" no longer allows the doctype `Site Update` in the document read method, because no code reads the record.

## Impact

- Code: new module `src/fc_manager/jobs.py` (the shared watch). Changes in `deploy.py`, `update.py`, `migrate.py`, `apps.py`, `errors.py`, `cli/deploy.py`, `cli/update.py`, and the watch screens.
- FC API: no new method. `press.api.client.get` stays in the allowlist, because the deploy watch reads `Deploy Candidate Build` with it. The doctype `Site Update` leaves the document read allowlist (`api/client.py`).
- Tests: `test_deploy.py`, `test_update.py`, `test_migrate.py`, `test_apps.py`, the CLI tests for deploy and update, and new fixtures for the update jobs.
- Release: a minor version, because two exit codes change.
- Out of scope: reading finished jobs (`press.api.site.jobs` fails over GET; a POST read is a possible later spike). The "Pick another team" menu entry is a separate change.
