# Design

## Context

`cli/menu.py` runs the menu walk:
- `run()` loops over three steps: the team picker (only when `many`, which means the profile reaches more than one team), `_bench_step()`, and `_action_loop()`.
- `_action_loop()` returns `OTHER_BENCH` (entry "Pick another bench", or Esc) or `QUIT`. `run()` returns on `QUIT` and goes to the bench step on `OTHER_BENCH`.
- To get to the team picker, the user must press Esc at the action menu and again at the bench step. The menu shows this path nowhere.

The team list comes from `scope_teams()` once, at the start of `run()`. The team picker reuses that list, so a return to it needs no FC request.

## Goals / Non-Goals

**Goals:**
- A visible entry that goes from the action menu to the team picker in one pick.
- No change for a profile with one team.

**Non-Goals:**
- A new key binding.
- A refresh of the team list from FC. The list stays the one that `run()` read at the start.
- A team switch from inside an action walk.

## Decisions

### D1. New return value `OTHER_TEAM`
Add `OTHER_TEAM = "team"` next to `OTHER_BENCH` and `QUIT`. `_action_loop()` gets a keyword `many: bool`. When `many` is true, it adds `("Pick another team", OTHER_TEAM)` after "Pick another bench". In `run()`, a result of `OTHER_TEAM` sets `team = None` and continues the loop, so the next pass shows the team picker.

Alternative: put "Pick another team" in the bench step list. Rejected: the user is at the action menu when the user wants to change the team, and the bench step has only bench rows today.

### D2. Entry order
The order is: actions, "Pick another bench", "Pick another team", "Quit". The navigation entries go from the smallest step back to the largest, and "Quit" stays last, as in the README.

### D3. Entry hidden with one team
With one team, the team picker does not show, so the entry has no target. The entry is hidden, not shown as disabled. This keeps the one-team menu the same as in v1.2.1.

## Risks / Trade-offs

- [Team list is stale] A team that the user joined after `fcm` started does not show. Restart `fcm` to see it. This is the same as today.
- [Test of the entry list] `test_action_menu_names_the_direct_commands` checks the full entry list. It changes with this change, because the test fixture has many teams.

## Migration Plan

- One patch release. No config or data change.
- Rollback: install the previous version.
