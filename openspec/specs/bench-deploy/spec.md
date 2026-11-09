# bench-deploy Specification

## Purpose
Lets a user deploy app updates to one FC bench (release group) from the CLI, as the FC dashboard does, with a guided walk, a full preview, and an explicit typed confirmation. The user always knows the target and the changes before anything changes on FC.

## Requirements

### Requirement: Deploy command
The system SHALL provide `fcm bench deploy [BENCH]`. BENCH SHALL resolve by FC name or title, as for every other bench target. The command SHALL deploy to one bench only.

#### Scenario: Bench given by title
- **WHEN** the user runs `fcm bench deploy "ACME Prod"` and one bench has that title
- **THEN** the walk starts at the app step for that bench

#### Scenario: Bench missing on a terminal
- **WHEN** the user runs `fcm bench deploy` in a terminal with no bench and no `--team`
- **THEN** the system first shows a picker of the teams, each with its label and owner email, and then a picker of the benches of the picked team only

#### Scenario: Esc on the bench step
- **WHEN** the user presses Esc on the bench picker after a team pick
- **THEN** the system shows the team picker again

### Requirement: Scoped queries
Each step of the walk SHALL query FC only inside the selections already made. After the bench is known, the system SHALL send every FC request for the deploy to that bench's team only, and SHALL NOT query other teams.

#### Scenario: After the bench pick
- **WHEN** the user picks bench `bench-1234` in team `acme`
- **THEN** every later request in the command carries `X-Press-Team: acme` and is about bench `bench-1234`

#### Scenario: Team given
- **WHEN** the user runs `fcm bench deploy --team acme` with no bench
- **THEN** the system skips the team step and lists benches of team `acme` only

#### Scenario: Team picked
- **WHEN** the user picks team `acme` at the team step
- **THEN** the system requests the benches of team `acme` only, and no other team

### Requirement: Nothing to deploy
When FC reports no available app update and no removed app for the bench, the system SHALL say so and exit with code 0 without a write. When FC reports a deploy in progress for the bench, the system SHALL say so, show its state, and exit with code 2 without a write.

#### Scenario: Bench is up to date
- **WHEN** the user picks a bench that has no update
- **THEN** the system prints that the bench is up to date and sends no write request

#### Scenario: Deploy already running
- **WHEN** the user picks a bench with a deploy in progress
- **THEN** the system prints the running deploy state, suggests `fcm bench show <bench>`, and exits with code 2

### Requirement: App update selection
The system SHALL show each app with an available update: app name, current version and next version (the release tag; else the version in a FC release message such as "Bumped to Version 16.55.2"; else the short commit hash), and a note when the branch changes. All apps with an available update SHALL be selected by default. The user MAY clear any of them. The system SHALL deploy the next release that FC offers for each selected app, and SHALL NOT offer a yanked release.

#### Scenario: Default selection
- **WHEN** FC reports updates for `erpnext` and `hrms`
- **THEN** both apps are selected when the app step opens

#### Scenario: No app selected
- **WHEN** the user clears every app and FC reports no removed app
- **THEN** the system does not continue to the confirmation and tells the user to select at least one app

### Requirement: Site selection with none by default
The system SHALL show the active and broken sites on the bench, as FC reports them, at a separate step. No site SHALL be selected by default. The step SHALL be shown even when no site is to be selected. When no site is selected, the deploy SHALL go to the bench only: the sites stay on the old bench.

#### Scenario: Default is no site
- **WHEN** the site step opens for a bench with 3 sites
- **THEN** none of the 3 sites is selected

#### Scenario: Bench-only deploy
- **WHEN** the user selects no site and confirms
- **THEN** the deploy request names no site, and the preview says "Bench only: no site is updated"

#### Scenario: Site update after build
- **WHEN** the user selects site `erp.acme.com` and confirms
- **THEN** the deploy request names `erp.acme.com`, with backups on and failing patches not skipped

### Requirement: Preview before confirmation
Before the confirmation, the system SHALL show a preview with: the profile, the team label and team name, the team owner email, the bench title and bench name, each selected app from current version to next version, each removed app, and the selected sites or "Bench only". The preview SHALL be the last output before the confirmation prompt.

#### Scenario: Preview content
- **WHEN** the user reaches the confirmation
- **THEN** the preview shows the profile, the team with its owner, the bench, every selected app with its versions, and the site list or "Bench only"

### Requirement: Typed confirmation
In interactive mode, the system SHALL start the deploy only after the user types the bench title exactly. Any other input SHALL cancel the deploy with exit code 2 and no write. In non-interactive mode, the system SHALL start the deploy only when `--confirm` equals the bench FC name. The system SHALL NOT provide a `--yes` option for a deploy.

#### Scenario: Correct title typed
- **WHEN** the user types the bench title exactly
- **THEN** the system sends the deploy request

#### Scenario: Wrong text typed
- **WHEN** the user types anything else, or presses Enter on an empty line
- **THEN** the system prints that the deploy was cancelled, sends no write request, and exits with code 2

#### Scenario: Script without confirm
- **WHEN** a script runs `fcm bench deploy bench-1234 --all-apps --json` with no `--confirm`
- **THEN** the system exits with code 2, sends no write request, and the error says that `--confirm bench-1234` is required

#### Scenario: Script with wrong confirm
- **WHEN** a script passes `--confirm bench-9999` for bench `bench-1234`
- **THEN** the system exits with code 2 and sends no write request

### Requirement: Non-interactive selection
In non-interactive mode, the system SHALL take the apps from `--app <name>` (repeatable) or `--all-apps`, and the sites from `--site <name>` (repeatable). With no `--site`, the deploy SHALL be bench only. A named app with no available update, or a named site that is not on the bench, SHALL be an error with exit code 2 and no write.

#### Scenario: Unknown site
- **WHEN** a script passes `--site other.example.com` and that site is not on the bench
- **THEN** the system exits with code 2, lists the sites on the bench, and sends no write request

#### Scenario: No app option
- **WHEN** a script passes neither `--app` nor `--all-apps`
- **THEN** the system exits with code 2 and sends no write request

### Requirement: Dry run
The system SHALL accept `--dry-run`. With `--dry-run`, the system SHALL run the walk and show the preview, and SHALL NOT ask for confirmation or send any write request.

#### Scenario: Dry run
- **WHEN** the user runs `fcm bench deploy bench-1234 --all-apps --dry-run`
- **THEN** the system prints the preview, exits with code 0, and sends no write request

### Requirement: Deploy progress
After FC accepts the deploy, the system SHALL follow the deploy until it reaches a final state, and SHALL show the current state and the build steps as they change. The system SHALL poll FC no more often than every 2 seconds. Ctrl+C SHALL stop the watch only: the system SHALL say that the deploy continues on FC and suggest `fcm bench show <bench>`. The system SHALL accept `--no-wait` to return right after FC accepts the deploy.

#### Scenario: Watch to the end
- **WHEN** FC accepts the deploy
- **THEN** the system shows each build step and its state until the deploy succeeds or fails

#### Scenario: Ctrl+C during the watch
- **WHEN** the user presses Ctrl+C while the system follows the deploy
- **THEN** the system prints that the deploy continues on FC, names `fcm bench show <bench>`, and sends no cancel request to FC

### Requirement: Watch liveness
On a terminal, the deploy watch SHALL show proof that FC still answers: the time since the last FC answer to a poll, the poll count, the elapsed time, and how long the current step has run. These values SHALL come from real FC answers. The time since the last answer SHALL grow while a poll gets no answer. When FC gives no answer for 10 seconds or more, the system SHALL show a warning. The JSON and plain-text outputs SHALL print a line only when the FC data changes.

#### Scenario: Long build step on a terminal
- **WHEN** a build step runs for 5 minutes with no change in FC data
- **THEN** the status line shows "last FC answer N s ago" with N reset at each FC answer, the poll count goes up, and the step shows how long it has run

#### Scenario: FC stops answering
- **WHEN** no poll gets an answer from FC for 14 seconds
- **THEN** the status line shows "no answer from FC for 14 s" as a warning

#### Scenario: JSON output during a long step
- **WHEN** a script follows the deploy with `--json` and FC data does not change for 10 polls
- **THEN** stdout gets no new progress line for those polls

### Requirement: Deploy result
On success, the system SHALL print the bench, the deployed apps, and the updated sites, and exit with code 0. When FC rejects the deploy request, the system SHALL show the FC message and exit with the code of the error kind, and SHALL NOT retry. When the deploy fails on FC after FC accepted it, the system SHALL show the failed step and the FC message, and exit with code 8.

#### Scenario: Build fails
- **WHEN** the FC build fails at step `Install apps`
- **THEN** the system names the step, shows the FC message, and exits with code 8

#### Scenario: FC validation refuses the deploy
- **WHEN** FC answers the deploy request with a validation error, for example from its "will fail" check
- **THEN** the system shows the FC message, sends no second request, and exits with code 1

### Requirement: Site update wait
After the new bench is ready, the system SHALL wait until each selected site is on a new bench, because FC moves each site in a separate job. When FC does not confirm a site move within 30 minutes, the system SHALL say that the result is not known, name the site, and exit with code 6.

#### Scenario: Site moves after the bench is ready
- **WHEN** the new bench is ready, and selected site `erp.acme.com` is still on the old bench for some polls
- **THEN** the system shows `erp.acme.com (waiting)`, keeps polling, and reports the site as updated when FC moves it

#### Scenario: Site move not confirmed in time
- **WHEN** selected site `erp.acme.com` is still on the old bench 30 minutes after the new bench is ready
- **THEN** the system says that FC did not confirm the update of `erp.acme.com`, says that its result is not known, and exits with code 6

### Requirement: Bench detail
The system SHALL provide `fcm bench show [BENCH]`. With no BENCH on a terminal, it SHALL use the same team-then-bench walk as `fcm bench deploy`. It SHALL show the team, the bench title and name, the Frappe version, the status, each app with its current version and any available update, the sites on the bench, and the state of a running deploy with its build steps. `fcm bench show` SHALL NOT change any state on FC.

#### Scenario: Bench with a running deploy
- **WHEN** the user runs `fcm bench show bench-1234` while a deploy runs
- **THEN** the system shows the deploy state and the current build step

#### Scenario: Bench detail as JSON
- **WHEN** the user runs `fcm bench show bench-1234 --json`
- **THEN** stdout is one JSON object with the bench, its apps with update fields, its sites, and the deploy state
