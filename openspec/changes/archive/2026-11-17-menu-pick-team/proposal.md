# Proposal

## Why

One FC login often reaches many teams (the team picker shows each team by its owner email). After the user picks a team, the action menu shows only "Pick another bench" and "Quit". The only way back to the team picker is Esc twice (action menu, then bench step), and the menu does not show that path. Users think that the menu cannot change the team.

## What Changes

- The action menu gets the entry "Pick another team", after "Pick another bench" and before "Quit".
- The entry shows only when the profile reaches more than one team. With one team, the action menu stays as it is today.
- The entry opens the team picker of the menu walk. It sends no request to FC before the team picker shows.
- Esc keeps its current behavior (one step back). This change adds no new key.
- The README menu section shows the new entry.

No breaking change. Scripts do not use the menu, so no exit code changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `interactive-menu`: the "Action menu" requirement adds the "Pick another team" entry, and it shows only when the profile reaches more than one team.

## Impact

- Code: `src/fc_manager/cli/menu.py` (`_action_loop()` entries and its return values, the `run()` loop).
- Tests: `tests/test_menu.py`.
- Docs: `README.md` (menu screen example and the step list), `CHANGELOG.md`.
- Version: next patch version (1.2.2 if it ships before `site-job-finder`, else the patch after 1.3.0).
- No FC API change and no allowlist change.
- Out of scope: a team switch from inside an action, a "recent teams" list, and a team pick by typed owner email in the menu.
