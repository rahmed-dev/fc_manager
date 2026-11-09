# Proposal

## Why

In `fcm bench deploy`, the user cannot tell whether a word after a space is a sub-command or an argument. The maintainer wants one rule: a space always means an argument or a flag follows. The maintainer also wants to pick the team and the bench once, and then choose what to do with that bench. Today, each command starts its own walk. The change comes now because only 10 commands exist. The rename costs more with each new write action (`site-migrate`, `site-update`, add app), and those actions come next.

## What Changes

- **BREAKING**: Every command gets one hyphenated name of the form `<noun>-<verb>`: `profile-add`, `profile-list`, `profile-test`, `profile-remove`, `team-list`, `bench-list`, `bench-show`, `bench-deploy`, `site-list`, `site-show`. The old two-word forms are removed. No alias is kept.
- An old two-word form (`fcm bench list`) gives a usage error, exit code 2, that names the new command (`fcm bench-list`). A plural noun (`fcm sites`) also names the new command (`fcm site-list`).
- `fcm --help` shows one flat list, grouped by noun (Profile, Team, Bench, Site).
- New interactive menu: `fcm` with no arguments on a terminal opens a walk. The walk is: team, then bench, then an action menu for that bench. The actions are `bench-show` and `bench-deploy`, plus "Pick another bench" and "Quit".
  - Every prompt in the menu shows the target path: profile > team > bench.
  - Each action runs the same code as its direct command, with the same preview and typed confirmation for a write.
  - After an action ends, with or without an error, the menu shows the action menu of the same bench again.
  - Esc goes back one step. Esc at the team step quits.
- `fcm` with no arguments, not on a terminal, prints the help and exits 0, as today.
- Out of scope: new write actions (`site-migrate`, `site-update`, add app), site-level actions in the menu, and a `site-show` team-first walk. Each one is a later change.

## Capabilities

### New Capabilities
- `interactive-menu`: the `fcm` no-argument walk (team, bench, action menu), the target path on each prompt, the return to the action menu, and Esc navigation.

### Modified Capabilities
- `cli-output`: the command grammar becomes `fcm <noun>-<verb>`. The old-form and plural-form errors name the new command. Help is grouped by noun. Every scenario uses the new names.
- `cloud-inventory`: no behavior change. The scenarios use the new command names.
- `credential-profiles`: no behavior change. The scenarios use the new command names.
- `bench-deploy`: no behavior change. The requirement text and the scenarios use the new command names (`bench-deploy`, `bench-show`).
- `fc-api-access`: no behavior change. One scenario names `fcm bench-show <bench>`.

## Impact

- Code: `src/fc_manager/cli/app.py` (root group, registration, old-form error, menu entry), `cli/profile.py`, `cli/inventory.py`, `cli/deploy.py` (command names; the show and deploy bodies become functions that the menu can call with a bench), and a new `cli/menu.py`.
- Hints and messages that name a command (for example "Run: fcm bench show <bench>") change to the new names.
- Tests: every CLI test that calls a command, and the integration command lists.
- Docs: `README.md`, and the `bin/fcm-dev` usage text if it names a command.
- Users: a script that calls a two-word form breaks, and the error names the new command. The tool has one user and no release, so no alias period is needed.
- FC: no change. The menu sends the same requests as the direct commands. No new FC method.
