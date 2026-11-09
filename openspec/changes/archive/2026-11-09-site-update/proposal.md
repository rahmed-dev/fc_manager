# Proposal

## Why

After a bench deploy, a site can stay on the old bench version. FC then shows "update available" for that site. `bench-deploy` moves sites only during a deploy, and `bench-deploy` sends no site by default. The maintainer must then go to the FC dashboard to update each site that stayed behind. `site-update` closes that gap. It is the second site action, and it uses the generic menu and the site step from `site-migrate`.

## What Changes

- New direct command `fcm site-update [SITE]`. It sends one FC update request for one site, after a preview and a typed confirmation. FC moves the site to the newest bench of its bench group and runs the migrate.
  - Options: `--skip-failing-patches`, `--confirm <site>`, `--dry-run`, `--no-wait`, `--team`, `--json`, `--debug`, `--profile`.
  - With no SITE in interactive mode, a picker walks team, then bench, then site. The site step lists only the sites that have an update.
  - A check before the preview reads the FC update info of the site:
    - A site with no update ends with a message and exit code 0, and no write.
    - A site in a status other than Active or Inactive is refused with exit code 2.
    - A site with an FC job in progress is refused with exit code 2.
  - The preview shows each app with its current and next version, and the failing-patch mode.
  - The typed confirmation is the site name. A script must pass `--confirm` equal to the site name. There is no `--yes`.
  - FC always takes its backup before the update. `fcm` does not offer a `--skip-backups` option (decision by Riz, 2026-11-09).
  - A watch follows the FC "Site Update" record step by step, with the same liveness line as the other watches.
  - Exit codes:
    - 0 when the update succeeds;
    - 8 when it fails, also when FC restores the site to the old bench (Recovered);
    - 6 when FC does not confirm the request.
- The menu gets the site action "Update a site (site-update)". A site action can now narrow its site step with a filter. "Update a site" lists only the sites that have an update.
- New FC methods and doctype on the allowlists:
  - write: `press.api.site.update`;
  - read: `press.api.site.check_for_updates`;
  - document read: the doctype `Site Update`, read by name through `press.api.client.get`.
- `update` joins `deploy` and `migrate` in the fixed set of write verbs.
- The spike script gets a read-only call to `check_for_updates`; Claude runs it. The `Site Update` fixture stays synthetic: FC list reads fail over GET, so no past update can be read. The maintainer runs the live checks through `bin/fcm-dev` (the menu) only.
- Out of scope:
  - updating many sites in one run;
  - scheduled updates, and editing or cancelling a scheduled update;
  - moving a site to another bench group or Frappe version;
  - skipping the FC backup;
  - add app.

## Capabilities

### New Capabilities
- `site-update`: the `fcm site-update` command, its checks, preview, typed confirmation, dry run, update watch and result.

### Modified Capabilities
- `interactive-menu`: the "Update a site" entry, and a site step that a site action can narrow to the sites that have an update.
- `fc-api-access`: the write allowlist gets `press.api.site.update`, which belongs to `site-update`. The read allowlist gets `press.api.site.check_for_updates` and the document read of `Site Update`. A new scenario covers an update request that times out.
- `cli-output`: the write verb set becomes `deploy`, `migrate` and `update`. The help lists `site-update` in the Site group. Exit code 8 also covers a failed site update.

## Impact

- Code:
  - new `src/fc_manager/update.py` (service: checks, request, watch of the Site Update record);
  - new `src/fc_manager/cli/update.py` (command and work function);
  - `cli/menu.py` (new action, site filter);
  - `cli/inventory.py` (`choose_site` filter);
  - `cli/root.py` (`WRITE_VERBS`);
  - `api/client.py` (allowlists, `READ_DOCTYPES`, follow-up hint);
  - `errors.py` (update errors);
  - `scripts/fc_spike.py`.
- Tests: new service, CLI and menu tests. The integration lists (canary and allowlist walk) get `site-update`.
- Docs: `README.md` (command, menu, exit codes, allowlist).
- FC: one new write request, `POST press.api.site.update`, only after the typed confirmation. FC deactivates the site, takes a backup, moves the site to the new bench and runs the migrate. A failed update can restore the site to the old bench (Recovered), or leave the site broken (Fatal).
