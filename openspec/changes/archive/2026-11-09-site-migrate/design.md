# Design

## Context

See proposal.md - Why. Current state:

- `cli/menu.py` holds a fixed `ACTIONS` list. `_action_loop` sends each action to its work function with an `if`/`else`. The walk has no site step.
- `cli/deploy.py` holds the bench work functions (`show_bench`, `deploy_bench`) and the deploy watch screen `_WatchView`. `_WatchView` reads `DeployState` fields directly (`stage`, `steps`, `checked_at`, `polls`, `current_step`).
- `FCClient.write()` builds the "result not known" hint from `body["name"]` as a bench: `Run: fcm bench-show <name>`. For a site write, that hint names the wrong command.
- `site-show` resolves a site by name across the teams in scope. `Inventory.sites()` returns `Site` rows with a `bench` field.

FC facts from the press source (read-only spike, press `master`, 2026-11-09):

- `press.api.site.migrate(name, skip_failing_patches=False)` is `@protected("Site")`. It calls `Site.migrate()` and returns nothing. The doc method checks `fatal_site_update` and the status (Active, Broken, Inactive), creates an Agent Job of type "Migrate Site", and sets the site status to Pending.
- FC has no job list read that works over GET. Both candidates fail with HTTP 500 `AttributeError`, because FC uses the `filters` JSON string as a dict. The maintainer's spike runs on 2026-11-09 confirmed both:
  - `press.api.site.jobs(filters, ...)`: its `@protected("Site")` decorator calls `filters.values()`.
  - `press.api.client.get_list` on `Agent Job`: it calls `filters.get(...)`.
- FC shows an "Undelivered" job as "Pending".
- `press.api.site.job(job)` checks that the job belongs to the current team. It returns the same fields plus `steps` (`step_name`, `status`, `start`, `end`, `duration`, `output`).
- `press.api.site.running_jobs(name)` is `@protected("Site")` with a plain site name. It returns the Pending and Running jobs of a site as press `job_detail` rows: `id` is the job name, and `name` is the job type. The spike run gave HTTP 200 (an empty list: no job was running).

## Goals / Non-Goals

**Goals:**
- A menu that gets a new action from one registry entry, with no edit to the loop.
- One watch screen for the deploy and the migrate, with the same liveness line.
- The migrate write path with the same guards as the deploy: allowlist, POST only, no retry, typed confirmation.

**Non-Goals:**
- No multi-site migrate. One site per run keeps the confirmation one exact name.
- No plugin loading. The registry is a plain list in code.
- No change to the deploy behavior or output.

## Decisions

### D1. Action registry in `cli/menu.py`
An `Action` dataclass has `label`, `command`, `scope` ("bench" or "site"), and `run(s, team, bench, site, path)`. `ACTIONS` is a list of `Action` values plus the 2 fixed entries "Pick another bench" and "Quit". `_action_loop` looks up the picked action. For scope "site", the loop runs the site step first and then calls `run`. The entry label is built as `"<label> (<command>)"`, so every entry names its direct command by construction.
- Alternative: each command module registers its own action with a decorator. Rejected for now: 3 actions do not need import-time registration, and a plain list shows the menu order in one place.

### D2. Site step lists sites of one bench
The site step calls `Inventory.sites([team])` and keeps the rows where `site.bench == bench.name`. This is one read for one team, the same read as `site-list --bench`.
- Alternative: use the `sites` rows of `bench.deploy_information`. Rejected: that read is for the deploy, and it does not give the site status.

### D3. Migrate service in `src/fc_manager/migrate.py`
`MigrateService(client)` has:
- `check(site)`: reads `press.api.site.get` for the status and `press.api.site.running_jobs` for jobs in Pending or Running state. It raises `UsageError` (exit 2) for a status outside Active, Inactive, Broken, or for a job in progress. It returns a `MigratePlan` (site, status, skip flag).
- `start(plan)`: one `client.write("press.api.site.migrate", team, name=site, skip_failing_patches=flag)`.
- `watch(plan, sleep, poll_seconds, clock)`: a generator like `DeployService.watch`. It yields a `MigrateState` after every FC answer.
  1. Find: poll `running_jobs` until a job of type "Migrate Site" shows up. After `FIND_LIMIT_SECONDS = 120` with no such job, raise a "result not known" error (exit 6) that shows the site status on FC.
  2. Follow: poll `job(job=name)` until the job status is Success or Failure.
  3. End: one `site.get` read gives the final site status for the result line.

The check refuses a site with a job in progress, so the "Migrate Site" job that shows up after the request is the job of this request. The job type match avoids a match on another job, for example a backup that FC starts at the same time.
- Alternative: a job list with ended jobs (`press.api.site.jobs` or `press.api.client.get_list`), with a baseline job noted before the request. Rejected: both fail over GET (see Context), and fcm sends reads as GET only. A read over POST would mix reads into the write path.
- Trade-off: `running_jobs` shows only Pending and Running jobs. A migrate that starts and ends between 2 polls (2 s), or that stays "Undelivered" for 2 minutes, is not seen. The watch then exits 6 with the site status, and does not claim success.
- Alternative: match the job by its creation time. Rejected: it depends on the clocks of FC and of the user's machine.

### D4. A generic watch screen
`_WatchView` moves from `cli/deploy.py` to a new `cli/watch.py`. It reads a small protocol that both `DeployState` and `MigrateState` give: `title_stage` (text), `steps`, `current_step`, `final`, `checked_at`, `polls`, and an optional `extra` line (the deploy "Sites:" line). The deploy keeps its output unchanged. The deploy tests for `_WatchView` move with it.
- Alternative: copy `_WatchView` for the migrate. Rejected: two copies of the liveness logic drift apart, and Riz asked for a status that is true, not cosmetic.

### D5. Per-method hint for an unconfirmed write
`FCClient.write()` gets the hint from a fixed map: `deploy_and_update` gives `Run: fcm bench-show <name>`, and `site.migrate` gives `Run: fcm site-show <name>`. The message names the job kind ("deploy" or "migrate").

### D6. No job list read on the allowlist
The allowlist holds `press.api.site.running_jobs` and `press.api.site.job` only. Both take a plain name, so no filter guard is needed. `press.api.site.jobs` and `press.api.client.get_list` stay off the allowlist, and a test checks that the client refuses them. An unused generic read would widen what `fcm` can read for no gain.

### D7. Command and work function in `cli/migrate.py`
`migrate_site(s, site, opts, *, in_menu=False, path=None)` holds the checks, preview, confirmation, request and watch. It raises `WatchStopped` in the menu after Ctrl+C, and exits 130 outside the menu, as `deploy_bench` does. The command `site-migrate` resolves the site (the same resolution as `site-show`), or walks team, bench, site in interactive mode, and then calls `migrate_site`. The menu calls `migrate_site` with the picked site. `WRITE_VERBS` gets `migrate`.

## Risks / Trade-offs

- [The FC job type name "Migrate Site" can change in press] The spike fixtures pin it, and the find step fails with exit 6 and a clear message, not a hang. Task 1 checks it on a real site.
- [A failed migrate can leave the site Broken on FC] The preview says what the migrate does. The result line shows the final site status, so the user sees "Broken" at once.
- [`--skip-failing-patches` hides a data problem] It is off by default. The preview shows a warning when it is on, and the menu never turns it on.
- [A fast migrate is not seen by `running_jobs`] The watch exits 6 with the site status, and does not claim success. Task 7.2 shows how long a real migrate job stays visible.
- [`press.api.site.job` and the step names are not confirmed on the live API: no job was running during the spike] Task 7.2 checks them on the first real migrate. `site_job.json` stays synthetic until then.
- [Moving `_WatchView` can change the deploy screen] The existing deploy watch tests run against the moved class with no change to their expected text.

## Migration Plan

No data migration. The change adds one command and one menu entry. Rollback is a revert of the commit. FC needs no change.

## Open Questions

- Does FC let a migrate start while a deploy updates the same site? The check refuses a site with a job in progress, so the answer does not change the code. The answer only changes the error text.
