# Tasks

## 1. Menu entry

- [x] 1.1 In `src/fc_manager/cli/menu.py`, add `OTHER_TEAM = "team"`. Give `_action_loop()` the keyword `many`, and add the entry `("Pick another team", OTHER_TEAM)` after "Pick another bench" when `many` is true (design D1, D2). Verify: `uv run ruff check` passes.
- [x] 1.2 In `run()`, pass `many` to `_action_loop()`. On `OTHER_TEAM`, set `team = None` and continue the loop. Verify: the module docstring and the `_action_loop()` docstring name the new return value.

## 2. Tests

- [x] 2.1 In `tests/test_menu.py`, update `test_action_menu_names_the_direct_commands` with "Pick another team" between "Pick another bench" and "Quit". Verify: the test passes.
- [x] 2.2 Add `test_other_team_entry_goes_to_team_step`: pick team `acme`, bench `bench-1234`, "Pick another team", then a second team and one of its benches. Verify: the prompt names are Team, Bench, Action, Team, Bench, Action; the second bench list holds the benches of the second team only; no request goes to FC between the action pick and the team prompt.
- [x] 2.3 Add a test with a profile that reaches one team. Verify: the menu starts at the bench step, and the action menu ends with "Pick another bench" and "Quit", with no "Pick another team".

## 3. Docs and release

- [x] 3.1 In `README.md`, add "Pick another team" to the menu screen example and to step 3 of the step list, with a note that it shows only for a profile with more than one team. Verify: the README entry order matches the code.
- [x] 3.2 Run `uv run pytest` and `uv run ruff check`. Verify: both pass.
- [x] 3.3 Ask Riz to open `bin/fcm-dev`, pick a team and a bench, pick "Pick another team", and pick a second team. Verify: Riz confirms that the team picker opens and that the bench list belongs to the second team.
- [x] 3.4 Set the next patch version in `pyproject.toml` (1.2.2, or the patch after 1.3.0 if `site-job-finder` ships first), and add a CHANGELOG entry under "Added". Verify: `fcm --version` prints the new version.

## Workflow follow-up

- Archive the change with `/opsx:archive` after Riz approves the live run of task 3.3.
