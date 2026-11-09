# Proposal

## Why

The maintainer tested the menu live on 2026-11-09 and found 3 problems:

- The deploy app step checks every app update by default. The maintainer usually deploys 1 app, so each deploy starts with clearing the other apps.
- In the pickers, a checked row gets a grey reverse background. The text on it is hard to read.
- The site step of "Update a site" is a single-select list. Enter picks a site, but Space does nothing visible, while Space toggles a row in the deploy steps. With 1 site in the list, the step also asks for a choice that does not exist.

## What Changes

- The `bench-deploy` app step opens with no app checked. The user checks the apps to deploy with Space. With no app checked, the existing message "Select at least one app to deploy." shows and the step opens again. `--app` and `--all-apps` do not change.
- One picker style for all pickers: a checked row keeps the normal background and gets a coloured mark; the row under the pointer is bold.
- The site step (menu and the no-SITE walk of `site-migrate` and `site-update`):
  - When exactly 1 site is left after the filter, the system picks it without a prompt and prints which site it picked.
  - With 2 or more sites, Space also picks the site under the pointer, the same as Enter.
- README: the deploy walk text and the site step text.
- Out of scope: the multi-site update; a change to the preview, the typed confirmation or any FC request; a change to the team, bench and action pickers other than the style.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `bench-deploy`: no app update is selected by default.
- `interactive-menu`: the site step picks the only site without a prompt, and Space picks the site under the pointer.

## Impact

- Code: `cli/picker.py` (style, Space key option), `cli/deploy.py` (app default), `cli/inventory.py` (`choose_site` auto-pick).
- Tests: deploy app step, site step, menu and the no-SITE walks.
- Docs: `README.md`.
- FC: no change. No new request, and no change to the write guards.
