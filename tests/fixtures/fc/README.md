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
| `error_permission.json` | - | SYNTHETIC: FC gave no error for an unknown team, so no real body exists yet. |

Never commit a fixture that holds a real email, IP address, host name, API key or secret.
