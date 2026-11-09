# Design

## Context

See proposal.md - Why. Current state:

- `cli/picker.py` has `choose()` (questionary `select`, type-to-filter, Enter picks, Esc goes back through `_bind_back`) and `choose_many()` (questionary `checkbox`, Space toggles, `selected` sets the default of every row). Neither passes a style.
- questionary marks a checked row and its mark with the style class `selected`, and the row under the pointer with `highlighted`. questionary sets `selected` to an empty style, so the prompt_toolkit default for `selected` applies: `reverse`. That default gives the grey background.
- `cli/deploy.py` `_choose_apps` calls `choose_many(..., selected=True)` and loops with "Select at least one app to deploy." when nothing is checked and FC reports no removed app.
- `cli/inventory.py` `choose_site` filters the sites of the bench (`only`), prints `empty` when none is left, and else calls `choose()`. `walk_to_site` (direct commands) and the menu site step both use `choose_site`.

## Goals / Non-Goals

**Goals:**
- Deploy starts with no app checked.
- Checked rows are easy to read on dark and light terminals.
- The site step needs no key press when only 1 site is possible, and Space acts as Enter there.

**Non-Goals:**
- No change to the preview, the typed confirmation, or any FC request.
- No multi-site update.
- No Space binding in the team, bench or action pickers: bench titles can hold spaces, and Space must stay a filter character there.

## Decisions

### D1. App default
`_choose_apps` passes `selected=False`. The empty-pick loop stays as it is. The instruction line of the checkbox already says "Space to toggle".

### D2. One picker style
`picker.py` defines one `questionary.Style` and passes it to `select` and `checkbox`:
- `selected`: `noreverse fg:ansigreen` (the checked mark and the checked row text, no background);
- `highlighted`: `bold` (the row under the pointer);
- `pointer`: `fg:ansicyan bold`.
ANSI colour names follow the terminal theme, so the rows stay readable on light and dark themes.
- Alternative: drop the row colour and show only the mark. Rejected: a coloured row is faster to scan when 5 apps are listed.

### D3. Site step auto-pick
`choose_site` returns the only row, with no prompt, when exactly 1 row is left after the filter. It prints `Site: <name>  (<status>)` first, so the user sees the target. The preview and the typed site name still come before any write. Esc in a later step does not reach the site step, so the back logic does not change.
- Alternative: keep the prompt for 1 site. Rejected by the maintainer (live test, 2026-11-09).

### D4. Space picks in the site step
`choose()` gets `space_picks: bool = False`. When true, a key binding on Space ends the prompt with the row under the pointer, as Enter does. Only `choose_site` passes true. FC site names hold no space, so the filter loses nothing. The instruction line then says "Enter or Space to pick".

## Risks / Trade-offs

- [The auto-pick hides that other sites exist] The filter is part of the message source: for "Update a site", the printed line names the only site with an update. The other sites have no update, so the user cannot pick them anyway.
- [A user expects Space to toggle, then presses Enter] In the site step both keys pick, so either key gives the same result.
- [The deploy now needs one more key press for "all apps"] The user can type Space on each row, or use `--all-apps` in a direct command. The maintainer prefers this default.

## Migration Plan

No data migration. Rollback is a revert of the commit.

## Open Questions

None.
