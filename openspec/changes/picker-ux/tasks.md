# Tasks

## 1. Picker

- [x] 1.1 Add one questionary style to `cli/picker.py` (design D2) and pass it to `choose()` and `choose_many()`. Verify with a unit test that both prompts get the style, and that `selected` has no `reverse`.
- [x] 1.2 Add `space_picks` to `choose()` (design D4): a Space key binding that picks the row under the pointer, and the instruction "Enter or Space to pick". Verify with a unit test that the binding exists only when `space_picks` is true.

## 2. Deploy app step

- [x] 2.1 `_choose_apps` uses `selected=False` (design D1). Verify with fake-picker tests: the app step opens with no app checked; a pick of 1 app gives a plan with that app only; an empty pick with no removed app shows "Select at least one app to deploy." and the step again. Update the existing tests that expect all apps checked.

## 3. Site step

- [x] 3.1 `choose_site` auto-picks the only row and prints `Site: <name>  (<status>)` (design D3), and passes `space_picks=True` to `choose()`. Verify with tests: 1 site left gives no prompt and the message; 2 sites give the prompt with `space_picks`; the empty message and the filter work as before; the menu "Update a site" and "Migrate a site" with 1 site go to the preview; the no-SITE walk of `site-update` and `site-migrate` with 1 site goes to the preview.

## 4. Docs and checks

- [x] 4.1 Update `README.md`: the deploy walk step 2 (no app selected, check with Space), and the site step (the only site is picked, Space or Enter picks). Verify that `pytest`, `ruff check` and `./bin/openspec validate picker-ux --strict` pass.

## 5. Live check

- [x] 5.1 The maintainer runs `bin/fcm-dev` (the menu): the deploy app step opens with no app checked and the checked rows are readable; "Update a site" on a bench with 1 site with an update goes to the preview with no site list. The maintainer cancels at the typed confirmation, so nothing is sent. Done when the maintainer accepts the look and the flow. Result on 2026-11-09: the maintainer ran the check and accepted it.

## Workflow follow-up

- Commit on the maintainer's request, archive with `/opsx:archive`, and run `./bin/openspec validate --specs --strict`.
