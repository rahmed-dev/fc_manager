# Proposal

## Why

The maintainer runs `bench migrate` on FC sites from the FC dashboard, one site at a time, with no clear view of the target. `fcm` has no site action yet, and its menu stops at the bench: the action list is fixed in code and there is no site step. `site-migrate` is the first site action, so this change also makes the menu walk generic, with a real action to prove it.

## What Changes

- New direct command `fcm site-migrate [SITE]`. It sends one FC migrate request for one site, after a preview and a typed confirmation.
  - Options: `--skip-failing-patches`, `--confirm <site>`, `--dry-run`, `--no-wait`, `--team`, `--json`, `--debug`, `--profile`.
  - With no SITE in interactive mode, a picker walks team, then bench, then site.
  - A check before the confirmation refuses a site that FC does not let migrate (a status other than Active, Inactive or Broken) and a site that has an FC job in progress.
  - The typed confirmation is the site name. A script must pass `--confirm` equal to the site name. There is no `--yes`.
  - A watch follows the FC "Migrate Site" job step by step, with the same liveness line as the deploy watch.
  - Exit codes: 0 when the job succeeds, 8 when it fails, 6 when FC does not confirm the request or the job is not found.
- The menu walk becomes generic:
  - Each action registers its label, its direct command, its scope (bench or site), and its work function. The menu builds the action list from that registry.
  - A site action adds a site step after the action pick. The site step lists the sites of the picked bench only.
  - The path line grows to profile > team > bench > site.
  - Esc at the site step goes back to the action menu. After a site action, the menu shows the action menu of the same bench.
- The action menu gets the entry "Migrate a site (site-migrate)".
- New FC methods on the allowlists:
  - write: `press.api.site.migrate`;
  - read: `press.api.site.running_jobs` and `press.api.site.job`, to find and follow the migrate job.
- `migrate` joins `deploy` in the fixed set of write verbs.
- The spike script gets read-only calls for the 2 job methods, and its anonymizer gets the missing `deploy_candidate` field.
- Out of scope: migrating many sites in one run, `site-update` (move a site to a newer bench), add app, and scheduled migrates. Each one is a later change.

## Capabilities

### New Capabilities
- `site-migrate`: the `fcm site-migrate` command, its checks, preview, typed confirmation, dry run, job watch and result.

### Modified Capabilities
- `interactive-menu`: the action registry, the site step for site actions, the 4-part path, Esc at the site step, and the new "Migrate a site" entry.
- `fc-api-access`: the write allowlist gets `press.api.site.migrate`, and each write method belongs to one command. The read allowlist gets `press.api.site.running_jobs` and `press.api.site.job`. The "result not known" hint names the read command for the target of that write.
- `cli-output`: the write verb set becomes `deploy` and `migrate`. The help lists `site-migrate` in the Site group. Exit code 8 also covers a failed migrate job.

## Impact

- Code:
  - new `src/fc_manager/migrate.py` (service: checks, request, job watch);
  - new `src/fc_manager/cli/migrate.py` (command and work function);
  - `cli/menu.py` (registry and site step);
  - `cli/root.py` (`WRITE_VERBS`);
  - `api/client.py` (allowlists, per-method hint for an unconfirmed write);
  - `scripts/fc_spike.py`.
- Tests: new service, CLI and menu tests; the integration lists (canary and allowlist walk) get `site-migrate`.
- Docs: `README.md` (command, menu, exit codes).
- FC: one new write request, `POST press.api.site.migrate`, only after the typed confirmation. FC runs `bench migrate` on the site. A failed migrate can leave the site in the Broken status on FC.
