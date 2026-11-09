# Design

## Context

See proposal.md - Why. Current state:

- `site-migrate` gives the pattern: `migrate.py` (service: check, start, watch generator), `cli/migrate.py` (preview, typed confirmation, watch screen, `migrate_site` work function, `_walk_to_site`), and a menu `Action` with scope "site".
- `cli/inventory.py` `choose_site(s, bench, back, path)` lists the sites of one bench from `Inventory.sites([team])`. Each `Site` row already has `update_available`, read from `press.api.site.all`. So a site filter needs no new FC read.
- `cli/watch.py` `WatchView` and `steps_table` serve the deploy and the migrate watch.
- `FCClient.write()` takes the follow-up hint from `WRITE_FOLLOW_UP`. `READ_DOCTYPES` holds only `Deploy Candidate Build`.
- `errors.py` already has `SiteUpdateUnknown`. It belongs to the site wait of `bench-deploy` (exit 6). The new errors need other names.

FC facts from the press source (`frappe/press` `master`, read on 2026-11-09):

- `press.api.site.update(name, skip_failing_patches=False, skip_backups=False)` is `@protected("Site")`. It calls `Site.schedule_update()`. That method inserts a `Site Update` record with status Pending and returns the record name.
- The insert of the `Site Update` record validates the update:
  - It finds the destination bench from a `Deploy Candidate Difference` of the bench group. With none, it fails with "Could not find suitable Destination Bench".
  - It refuses an update when the site already has a pending update: "An update is already pending for this site".
  - It refuses an update when the destination bench lacks an app of the site.
  - FC returns these errors as a validation error, so `fcm` exits with code 1 and shows the FC message.
- `press.api.site.check_for_updates(name)` is `@protected("Site")` with a plain name. It returns `update_available`, and, when true, `apps`: one row per app with `app`, `title`, `current_hash`, `current_tag`, `next_hash`, `next_tag`, `branch`, `current_branch`, `will_branch_change` and `update_available`.
- `press.api.client.get` allows the doctype `Site Update` (press `ALLOWED_DOCTYPES`). The record gives its `dashboard_fields` (`status`, `site`, `source_bench`, `destination_bench`, `deploy_type`, `update_job`, `recover_job`, `update_start`, `update_end`, and others). Its `get_doc` hook adds `steps`: a list of `{name, title, status, output, stage}`. The steps come from up to 6 FC jobs in order: deactivate, backup, update ("Update Site"), restore, recover ("Recover Site"), activate.
- `Site Update.status` is one of Pending, Running, Success, Failure, Recovering, Recovered, Fatal, Scheduled, Cancelled.
  - Failure means the update failed and FC has not restored the site yet.
  - Recovering means FC restores the site to the old bench.
  - Recovered means FC restored the site.
  - Fatal means FC could not restore the site, and the site is Broken.
- The update job step "Move Site" is the point of no return in press.
- The FC site status shows "Updating" during the update.

## Goals / Non-Goals

**Goals:**
- `site-update` with the same guards as `site-migrate`: allowlist, POST only, no retry, preview, typed site name.
- A site step that a site action can narrow, with no new FC read.
- One walk to a site for both site commands.

**Non-Goals:**
- No change to the migrate or deploy behavior or output.
- No read of past `Site Update` records. FC list reads fail over GET, and the write returns the record name.

## Decisions

### D1. Watch the `Site Update` record by name
The write returns the record name. The watch polls `press.api.client.get(doctype="Site Update", name=...)` every 2 s, and shows the record status and its `steps`. The watch ends at Success, Recovered, Fatal or Cancelled. Failure and Recovering are not final: FC then starts its recover job, so the watch keeps polling and shows "FC restores the site".
- Alternative: find the FC job through `running_jobs`, as `site-migrate` does. Rejected: the update spans up to 6 FC jobs, and only the record shows them in one list. The record name also removes the find step and its 2-minute limit.
- Trade-off: a Failure with no recover job stays at Failure. A watch limit covers it: when the status stays Failure for 10 minutes with no `recover_job`, the watch ends with exit 8 and names the failed step. The hint names `fcm site-show <site>`.

### D2. Update service in `src/fc_manager/update.py`
`UpdateService(client)` has:
- `info(site)`: reads `check_for_updates` and returns an `UpdateInfo` (flag and `AppChange` rows).
- `check(site, skip_failing_patches)`: reads the info, the site status (`site.get`) and `running_jobs`. It raises `NothingToUpdate` (exit 0) when FC reports no update. It raises `UsageError` (exit 2) for a status outside Active and Inactive, or for a job in Pending or Running state. It returns an `UpdatePlan`.
- `start(plan)`: one `client.write("press.api.site.update", team, name=..., skip_failing_patches=..., skip_backups=False)`. It returns the record name. When the answer holds no string name, it raises `UpdateUnknown` (exit 6).
- `watch(plan, record, sleep, poll_seconds, clock)`: a generator that yields an `UpdateState` after every FC answer. At the end it reads the site status once.

`AppChange.current_version` is `current_tag`, else the short `current_hash`. `next_version` is the same for the next release. Only rows with `update_available` show in the preview.

The parser reuses `JobStep` from `migrate.py` for the steps, with `title` as the step label. `running_jobs` parsing comes from `migrate.parse_running_jobs`.

### D3. Status rule: Active and Inactive only
`fcm` refuses an update for a site in any other status, Broken included. A Broken site first needs a fix (for example `site-migrate`), and an update of a Broken site can fail with no clean recovery. FC itself does not check the status in `update()`. So this is a stricter local rule, and the error says so.
- Alternative: allow Broken, as `site-migrate` does. Rejected: an update deactivates the site and moves it, so the risk is larger than a migrate.

### D4. Exit 0 for "no update"
A site with no update is not an error: the target state is already true. The command prints "Site X has no update" and exits 0, as `bench-deploy` does for a bench with nothing to deploy. A `NothingToUpdate` signal (not an `FcmError`) carries it to the CLI.

### D5. Site filter on the site step
`choose_site` gets `only: Callable[[Site], bool] | None` and `empty: str | None` (the message when no site is left). `Action` gets an optional `site_filter`. "Update a site" sets `site_filter=lambda x: x.update_available` and the message "No site of bench X has an update.".
- Alternative: a separate `choose_site_with_update`. Rejected: 2 copies of the same picker.

### D6. One walk to a site
`_walk_to_site` moves from `cli/migrate.py` to `cli/inventory.py` as `walk_to_site(s, teams, only=None, empty=None)`. `site-migrate` calls it with no filter, and `site-update` with the update filter. Migrate behavior does not change, and its tests stay as they are.

### D7. Errors
- `UpdateFailed` (JOB_FAILED, exit 8), with `step` and `outcome` ("failure", "recovered" or "fatal").
- `UpdateUnknown` (SERVER, exit 6): the request was accepted, but the record name is missing.
- An unconfirmed write uses the existing `WriteUnknown` path, with `WRITE_FOLLOW_UP["press.api.site.update"] = ("update", "site-show")`.

### D8. Command and work function in `cli/update.py`
`update_site(s, site, opts, *, in_menu=False, path=None)` holds the check, preview, confirmation, request and watch, the same shape as `migrate_site`. `UpdateOptions` has `skip_failing_patches`, `confirm`, `dry_run` and `no_wait`. The watch screen is `WatchView("Update", ...)` with the stage text for Pending, Running, Recovering and the final states. `WRITE_VERBS` gets `update`.

### D9. Spike
Question 5 of `scripts/fc_spike.py` reads `check_for_updates` for the first site with `update_available` in `site.all`, over all teams. The anonymizer adds the hash fields of the app rows (`current_hash`, `next_hash`; the repository fields are already in it), and private app names are replaced. The spike never calls `press.api.site.update`. Claude runs the spike (read-only). The maintainer tests live through `bin/fcm-dev` (the menu) only.

The run of 2026-11-09 found 1 site with an update in 13 teams. FC refused all site reads for it with HTTP 403 (no permission for the key). So `site_check_for_updates.json` stays synthetic until task 7.1. A site like this one makes `site-update` exit with code 4 at the checks, with no write.

## Risks / Trade-offs

- [The `Site Update` step titles and the record shape are not confirmed on the live API] The fixture `site_update.json` is synthetic and built from the press source. The first live update through the menu confirms it. The parser tolerates missing fields.
- [An update deactivates the site for its duration] The preview says that FC takes the site down for the update and takes a backup first. The confirmation is the exact site name.
- [Fatal leaves the site Broken] The result shows the site status and tells the user to contact FC support. `fcm` does not try a recovery.
- [A Failure with no recover job never ends] The 10-minute limit in D1 ends the watch with exit 8.
- [`--skip-failing-patches` hides a data problem] It is off by default. The preview shows a warning. The menu never turns it on.
- [FC validation refuses the update (no destination bench, missing app)] `fcm` shows the FC message and exits 1, with no retry.

## Migration Plan

No data migration. The change adds one command and one menu entry. Rollback is a revert of the commit. FC needs no change.

## Open Questions

- What are the real step titles of a live update? The answer changes only the fixture, not the code.
