# FC API fixtures

Recorded from the live FC API (`https://cloud.frappe.io`) on 2026-11-09 with
`scripts/fc_spike.py`, then anonymized: names, titles, emails, IP addresses and host names
are placeholders, and any field whose name holds `key`, `secret`, `token` or `password` is
masked. Long commit messages are cut to their first line.

| File | Call | Notes |
| --- | --- | --- |
| `account_get.json` | `press.api.account.get` | Only `user` and `teams` kept; `_other_fields` lists the dropped fields. |
| `bench_all.json` | `press.api.bench.all` | Rows have no `team` field. |
| `site_all.json` | `press.api.site.all` | |
| `site_get.json` | `press.api.site.get` | |
| `site_installed_apps.json` | `press.api.site.installed_apps` | |
| `unknown_team_site_all.json` | `site.all` with a made-up `X-Press-Team` | HTTP 200, no rows. |
| `error_auth.json` | wrong secret | HTTP 401, `exc_type` only, no message. |
| `error_not_found.json` | `site.get` for a site that does not exist | HTTP **403** `PermissionError`, not 404. |
| `site_running_jobs.json` | `site.running_jobs` for one site | SYNTHETIC row: the spike run of 2026-11-09 gave HTTP 200 with an empty list (no job was running). The row has the shape of press `job_detail` (`id` is the job, `name` the job type). FC has no job list that works over GET: `site.jobs` and `client.get_list` both gave HTTP 500 `AttributeError`. |
| `site_job.json` | `site.job` for one job | SYNTHETIC: fields from the press source. The step names are a guess. The first real migrate (task 7.2) checks them. |
| `site_check_for_updates.json` | `site.check_for_updates` for one site | SYNTHETIC: fields from the press source (`frappe/press` `master`, 2026-11-09). Hashes are made up. Spike question 5 reads the real shape; its run of 2026-11-09 got HTTP 403 (no permission on the only site with an update), so the shape is not confirmed yet. |
| `site_job_update_failed.json` | `site.job` for a failed site update job | Real answer (read-only spike of 2026-11-17, job of a site update that a bench deploy started). Only the job name is replaced. It confirms the job type `Update Site Migrate`, the step `Backup Site Tables` with the output `mariadb-dump: Got error: 1040: "Too many connections"`, and the step status `Skipped` for the steps after a failure. |
| `site_job_recover.json` | `site.job` for the recover job after that failure | Real answer (read-only spike of 2026-11-17). Only the job name is replaced. One step, `Disable Maintenance Mode`; the job ran 0.57 s and started 3 s after the failed update ended, so a 2 s poll can miss it (design D3: the site status is the second source). |
| `bench_all_apps.json` | `bench.all_apps` for one bench group | Real shape (spike question 6, 2026-11-09): 388 rows, 191 with a source for the group version. Kept 20 rows; `image` and `description` dropped. A row with an empty `sources` list is not compatible with the group version. |
| `site_available_apps.json` | `site.available_apps` for one Active site | Real shape (spike question 6, 2026-11-09). No row had plans, so the plan fields (`has_plans_available`, `plans`, `billing_type`) are tested with rows built in the tests. |
| `site_job_install.json` | `site.job` for an install job | SYNTHETIC: the shape of `site_job.json` with the job type `Install App on Site`. The step names are a guess. The first real install (task 8.1) checks them. |
| `github_options.json` | `github.options` for one team | SYNTHETIC with the real keys (spike question 7, 2026-11-09: 5 installations, 5.8 kB). Repository names are private, so none is recorded. |
| `github_branches.json` | `github.branches` for one repository | SYNTHETIC rows with the real keys (`name`, `commit`, `protected`, ...); the spike read 356 rows for `frappe/crm`. |
| `github_app.json` | `github.app` for `frappe/crm` branch `main` | Real answer for a public repository (spike question 7). |
| `error_permission.json` | - | SYNTHETIC: FC gave no error for an unknown team, so no real body exists yet. |

Job type names of the site job watch (site-job-finder):

| Job type | Source |
| --- | --- |
| `Update Site Migrate` | Confirmed: live `site.job` answer of 2026-11-17 (`site_job_update_failed.json`). |
| `Recover Failed Site Update` | Confirmed: live `site.job` answer of 2026-11-17 (`site_job_recover.json`). |
| `Update Site Pull` | Not confirmed: from the press source only. |
| `Migrate Site`, `Install App on Site` | From the press source; the first live runs used them. |

Never commit a fixture that holds a real email, IP address, host name, API key or secret.
