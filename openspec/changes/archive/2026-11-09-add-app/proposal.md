# Proposal

## Why

`fcm` can deploy, migrate and update, but it cannot add an app. To add a marketplace app to a bench group, or to install an app on a site, the maintainer must still go to the FC dashboard. This change adds both steps as menu actions and direct commands. It is the last write action in the menu order that was approved on 2026-11-09.

## What Changes

- New direct command `fcm bench-add-app [BENCH]`. It adds apps to a bench group, after a preview and a typed confirmation. The first step asks where the app comes from (revised after the first menu check, Riz, 2026-11-09):
  - **From the marketplace:** a search prompt, not a long list. `fcm` reads the marketplace apps of the group once per bench and session, builds an index, and shows at most 10 ranked matches as the user types. The user can pick several apps; all go to FC in one `press.api.bench.add_apps` request. FC supports a list there, although the dashboard adds 1 app at a time.
  - **From GitHub:** a repository of the team's FC GitHub installations, or a pasted public URL; then a branch. FC reads the app name and Frappe version range of the branch. One GitHub app per run, sent as `press.api.client.run_doc_method` (`Release Group`, `add_app`), the same call as the dashboard.
  - Options: `--app <app>` (repeat), `--source <app>=<source>`, `--repo <url>`, `--branch <branch>`, `--confirm <bench>`, `--dry-run`, `--team`, `--json`, `--debug`, `--profile`.
  - The preview shows the bench, its Frappe version, and each app with its branch and repository. It says that the apps reach the benches only at the next deploy.
  - The typed confirmation is the bench title, as for `bench-deploy`. A script must pass `--confirm` equal to the bench FC name. There is no `--yes`.
  - FC records the apps and starts no job, so there is no watch. The command prints the hint `fcm bench-deploy <bench>`.
  - Exit codes: 0 when FC accepts the request; 6 when FC does not confirm it.
- New direct command `fcm site-install-app [SITE]`. It installs one app on one site, after a preview and a typed confirmation.
  - Options: `--app <app>`, `--confirm <site>`, `--dry-run`, `--no-wait`, `--team`, `--json`, `--debug`, `--profile`.
  - The app list comes from FC: the apps on the bench of the site that the site does not have.
  - An app with marketplace plans is shown as "has plans: install it from the FC dashboard" and cannot be picked. `fcm` never starts a paid subscription (decision by Riz, 2026-11-09).
  - A check before the preview: a site in a status other than Active is refused with exit code 2. A site with an FC job in progress is refused with exit code 2.
  - The typed confirmation is the site name. A script must pass `--confirm` equal to the site name.
  - A watch follows the FC job `Install App on Site` step by step, with the same liveness line as the other watches.
  - Exit codes: 0 when the install succeeds; 8 when the job fails; 6 when FC does not confirm the request.
- The menu gets the bench action "Add an app (bench-add-app)" and the site action "Install an app (site-install-app)". After an app is added from the menu, the menu asks "Deploy now?". A yes starts the existing deploy action of the same bench, with its own preview and typed confirmation.
- The app is an option (`--app`, or `--repo` for GitHub), not a second positional argument, because a command keeps one positional target. In a script, a missing app exits with code 2.
- The command grammar gets a third form, `<noun>-<verb>-<object>`, for these 2 commands only. The write verbs become `deploy`, `migrate`, `update`, `add-app` and `install-app`. The names follow Frappe's own `bench get-app` and `bench install-app`.
- New FC methods on the allowlists:
  - write: `press.api.bench.add_apps`, `press.api.client.run_doc_method` (only for `Release Group` and `add_app`), and `press.api.site.install_app`;
  - read: `press.api.bench.all_apps`, `press.api.site.available_apps`, `press.api.github.options`, `press.api.github.branches` and `press.api.github.app`.
- The spike script gets read-only calls to the app list reads and the GitHub reads; Claude runs it. The maintainer runs the live checks through `bin/fcm-dev` (the menu) only.
- Out of scope:
  - several GitHub apps in one run (FC takes one per request);
  - connecting a new GitHub installation (done in the FC dashboard);
  - removing an app from a bench group, and uninstalling an app from a site;
  - choosing or buying a marketplace plan;
  - changing the branch of an app.

## Capabilities

### New Capabilities
- `bench-add-app`: the `fcm bench-add-app` command, its source choice, marketplace search, GitHub repository and branch steps, preview, typed confirmation, dry run and result.
- `site-install-app`: the `fcm site-install-app` command, its checks, app list, preview, typed confirmation, dry run, job watch and result.

### Modified Capabilities
- `interactive-menu`: the 2 new entries in the action menu, the "Deploy now?" step after an add, and the return to the action menu after an install watch is stopped.
- `fc-api-access`: the write allowlist gets `press.api.bench.add_apps` and `press.api.client.run_doc_method` (both belong to `bench-add-app`; the second only for `Release Group` and `add_app`) and `press.api.site.install_app` (belongs to `site-install-app`). The read allowlist gets the app list reads and the GitHub reads. New scenarios cover a write request that times out for each.
- `cli-output`: the grammar allows the `<noun>-<verb>-<object>` form, the write verb set grows, the help lists the 2 new commands, and exit code 8 also covers a failed install.

## Impact

- Code:
  - new `src/fc_manager/apps.py` (service: app lists, search index, GitHub reads, checks, requests, install watch);
  - new `src/fc_manager/cli/apps.py` (2 commands and their work functions);
  - `cli/menu.py` (2 actions, "Deploy now?" step);
  - `cli/root.py` (`WRITE_VERBS`, grammar note);
  - `api/client.py` (allowlists, follow-up hints);
  - `errors.py` (install errors);
  - `scripts/fc_spike.py`.
- Tests: new service, CLI and menu tests. The integration lists (canary and allowlist walk) get the 2 commands. `test_cli_core.py` gets the new names.
- Docs: `README.md` (commands, menu, exit codes, allowlist).
- FC: 2 new write requests, each only after its typed confirmation.
  - `POST press.api.bench.add_apps` or `POST press.api.client.run_doc_method` changes the bench group record. A GitHub add also creates an App and an App Source record on FC. The benches do not change until the next deploy.
  - `POST press.api.site.install_app` runs an install job on the live site. FC sets the site to Pending during the job. A failed install can leave the app partly installed on the site.
