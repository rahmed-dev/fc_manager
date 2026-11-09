# Proposal

## Why

`fcm` can now find every bench and site across all FC teams, but the user still opens the FC dashboard to deploy an app update. A deploy is the most sensitive action on FC: it builds a new bench image and can move live sites onto it. This change adds the first write action, `fcm bench deploy`, with a guided walk, a full preview, and an explicit typed confirmation, so that the user always knows the target and the changes before anything happens on FC.

## What Changes

- New command `fcm bench deploy [BENCH]`. It follows the walk that the maintainer approved on 2026-11-09:
  1. Pick the team, then a bench of that team (skip the team step with `--team`, or both steps with a bench name).
  2. Pick the app updates (all available updates selected by default).
  3. Pick the sites to update after the build (**none selected by default**). With no site, the deploy goes to the bench only, as FC allows. The sites stay on the old bench and show "update available".
  4. Preview: profile, team (with owner), bench, each app from version to version, the sites to move or "bench only", and removed apps.
  5. Confirm: the user types the bench title. Nothing else starts the deploy.
  6. Execute, then follow the FC deploy until it ends, with the build steps on screen.
  7. Result: success, or the failed step with the FC message. Ctrl+C stops the watch, not the deploy.
- Each step of the walk queries FC only inside the selections already made. After the bench pick, every call goes to that one bench in its one team.
- Non-interactive form for scripts: `--app`, `--all-apps`, `--site`, and `--confirm <bench name>`. There is no `--yes`.
- `--dry-run` shows the preview and exits without a write.
- New command `fcm bench show [BENCH]`: the bench, its apps with available updates, its sites, and the state of a running deploy. The user runs it to look at a deploy after Ctrl+C.
- The API client gets a separate write allowlist with one method, `press.api.bench.deploy_and_update`. A write call is never retried. The read allowlist gets the deploy read methods.
- New exit code 8: FC accepted the deploy, but the deploy failed on FC.
- **Not in scope:** in-place update, patch deploy, the override of the FC "will fail" check, skip-backups and skip-failing-patches options, `fcm site update`, and the TUI. The faster team-first `site show` picker is a separate later change.

## Capabilities

### New Capabilities

- `bench-deploy`: deploy app updates to a bench on FC. This covers the walk, the scoped queries, the preview, the typed confirmation, the bench-only deploy, the progress watch, the result, and `fcm bench show`.

### Modified Capabilities

- `fc-api-access`: the read-only allowlist becomes a read allowlist plus a separate write allowlist. Write calls use POST and are never retried.
- `cli-output`: the fixed verb set gets the write verb `deploy`. The exit codes get code 8 for a deploy that FC accepted but that failed.

## Impact

- New code: `src/fc_manager/deploy.py` (deploy service, no CLI dependency), `src/fc_manager/cli/bench.py` or an extension of `cli/inventory.py`, and changes to `api/client.py`, `errors.py`, `cli/picker.py` (multi-select), and `cli/app.py`.
- FC API (from the public `frappe/press` source, confirmed by a read-only spike on 2026-11-09):
  - read: `press.api.bench.deploy_information`, `press.api.bench.deploy_status`, and `press.api.client.get` for the doctype `Deploy Candidate Build` only
  - write: `press.api.bench.deploy_and_update`
- Risk: this is the first change that can change FC. A wrong target or a wrong site list can update live sites. The walk, the preview, the typed confirmation, and the tests exist to stop that.
- No new runtime dependency is expected. `questionary` already has a multi-select (`checkbox`).
