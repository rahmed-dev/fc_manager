# Design

## Context

See proposal.md for the motivation. The current state:

- `migrate.watch_site_job()` (migrate.py) serves `site-migrate` and `site-install-app`. It polls `press.api.site.running_jobs` until a job of one type shows up, then polls `press.api.site.job` until that job ends. It follows one job only.
- `UpdateService.watch()` (update.py) reads the `Site Update` record by name through `press.api.client.get`. The record gives one status (Pending ... Recovered, Fatal, Cancelled) and the steps of up to 6 FC jobs.
- `DeployService.watch()` (deploy.py), after the bench is ready, compares the bench of each selected site with its bench before the deploy. It reads no job.
- FC has no job list that works over GET (`press.api.site.jobs` and `press.api.client.get_list` fail on the filters string; spike of 2026-11-09). `running_jobs` shows only Pending and Running jobs.
- The FC Jobs tab of 2026-11-17 for the failed site shows these job types around a deploy: "Backup Site", "Update Site Migrate" (Failure, 40 s), "Recover Failed Site Update" (Success, 0 s), "Update Site Configuration".

The design of the 2026-11-09 site-update change (D1) rejected `running_jobs` for the update, because the record shows all jobs in one list. This change reverses D1 on purpose: one finder for all actions is the decided scope, and the record cannot serve `bench-deploy`, because the deploy does not return the record names.

## Goals / Non-Goals

**Goals:**
- One module that finds and follows the jobs of one site, for all four actions.
- A failed site update in `bench-deploy` is reported within seconds of the job end, with the job, the step and the FC output.
- The outcome of a failed update (restored or not) does not depend on fcm seeing a short recover job.

**Non-Goals:**
- Reading finished jobs. A POST read of `press.api.site.jobs` is a possible later spike.
- A change to the checks, previews or confirmations of any action.
- The "Cancelled" outcome. FC jobs do not show it. A cancelled update shows no update job, so it ends as "not known" (exit 6).

## Decisions

### D1. New module `jobs.py` with one `SiteJobWatch`
The watch moves out of `migrate.py` into `src/fc_manager/jobs.py`. `JobRow`, `JobStep`, `parse_running_jobs`, `parse_job` and the `IN_PROGRESS` / `JOB_DONE` sets move with it. `migrate.py`, `apps.py`, `update.py` and `deploy.py` import from `jobs.py`.

The watch takes one site and a `JobSpec`:
- `expected`: the job types that end the find step ("Migrate Site"; "Install App on Site"; "Update Site Migrate" and "Update Site Pull").
- `find_limit`: 120 s, or 30 min for the deploy.
- `recover`: true for the update and the deploy. It turns on the recovery step (D3).

Alternative: keep `watch_site_job()` and add flags. Rejected: the function then does three things in a file named for one of them.

### D2. Follow every job, decide on the expected job
Each poll reads `running_jobs`. Every new job name goes into a set of followed jobs, and the watch reads each followed job with `site.job` until it ends. The state that the watch yields holds all followed jobs, so the screen shows "Backup Site" and "Update Site Migrate" as the dashboard does.

Only the expected job decides the result. An unrelated job that fails (for example "Update Site Configuration") is shown, but it does not end the watch.

The watch ends:
- with success when the expected job ends in Success;
- with failure when the expected job ends in Failure and `recover` is false;
- with the recovery step (D3) when the expected job ends in Failure and `recover` is true;
- with "not known" when no expected job shows up within `find_limit`.

Alternative: follow only the expected job, as today. Rejected: the user asked for the view of the Jobs tab, and the backup job is often the one that fails first.

### D3. Recovery outcome from the recover job and the site status
After the update job fails, FC starts a recover job. The 2026-11-17 recover job ran for 0 s, so `running_jobs` can miss it. So the outcome has two sources, and the first one that answers wins:
1. A followed job whose type starts with "Recover Failed Site" ends: Success gives "restored", Failure gives "not restored".
2. Each poll also reads the site status (`press.api.site.get`). Active or Inactive gives "restored". Broken gives "not restored". Any other status (Updating, Recovering, Pending) means wait.

When neither source answers within 10 minutes, the result is "failed, no recovery" (exit 8), as today.

Alternative: keep the `Site Update` record for this outcome. Rejected: the deploy has no record name, and two sources of truth are what this change removes.

### D4. Deploy follows all selected sites in one loop
After the bench is ready, the deploy runs one `SiteJobWatch` for each selected site. One loop steps each watch that is not done, one poll each, then sleeps 2 s. No thread. The deploy state gets a tuple of site results (site, stage, failed job, failed step, output, outcome) in place of the `(site, moved)` pairs.

The bench-change check goes away. A site update job in Success is the proof of the update.

Alternative: one thread for each site. Rejected: the poll count is small (one site in most deploys), and threads make the watch harder to test with the fake clock.

### D5. Deploy result and exit codes
`DeployService.watch()` ends normally when all sites succeed. When one or more sites failed, it raises `DeployFailed` (exit 8) with one line for each failed site. When no site failed and one or more sites are "not known", it raises `SiteUpdateUnknown` (exit 6). The result shows every site in all three cases. `--json` output gets one `sites` list with `site`, `result` (`updated`, `failed`, `unknown`), `job`, `step`, `output` and `outcome`.

### D6. Update result without the record
`UpdateService.start()` returns the record name when FC gives one, and an empty string when it does not. The CLI shows a record name that it gets. `UpdateUnknown` for a missing name goes away. `UpdateState` changes to the shape of the site job watch state; the stages are finding, waiting, running, recovering, success, recovered, fatal, failure. `parse_update_record`, `STAGES` for the record, and `RECORD_DOCTYPE` go away. `UpdateFailed.outcome` keeps "failure", "recovered" and "fatal", and loses "cancelled".

After success, the result does not name the new bench. The record gave `destination_bench`. `press.api.site.get` gives only `group` (the bench group), as the fixture `site_get.json` shows. One more read only for a name in the success text is not worth it.

### D7. Allowlist
The doctype `Site Update` leaves `READ_DOCTYPES` in `api/client.py`. No method is added.

## Risks / Trade-offs

- [The update job types are confirmed only from the dashboard. "Update Site Pull" and the "Recover Failed Site ..." prefix come from press, not from a live answer] The parser matches the types by name. A fixture from the first live run through `bin/fcm-dev` menu confirms them. A wrong name shows as "not known" (exit 6), not as a false success.
- [A short job is missed] Short jobs show nowhere in the result. The expected update and migrate jobs run for many seconds. D3 covers the short recover job. The short limit stays in the spec.
- [Site status Active after a failure can come from a fix by FC support, not from the recover job] The text says "FC restored the site", which is still what the user needs to know.
- [More requests during a deploy] One `running_jobs`, one `site.job` for each running job, and one `site.get` for each site in recovery, every 2 s. For the usual 1 to 3 sites, this is below the rate that the deploy watch uses now with the build reads.
- [Exit code change] A deploy with a failed site update now exits 8, not 6. Scripts that treat 6 as "check by hand" now see 8. The CHANGELOG says so.

## Migration Plan

- One minor release (v1.3.0). No config or data migration.
- Rollback: install the previous version. The FC side does not change.
