# Spec Delta

## MODIFIED Requirements

### Requirement: Deploy command
The system SHALL provide `fcm bench-deploy [BENCH]`. BENCH SHALL resolve by FC name or title, as for every other bench target. The command SHALL deploy to one bench only.

#### Scenario: Bench given by title
- **WHEN** the user runs `fcm bench-deploy "ACME Prod"` and one bench has that title
- **THEN** the walk starts at the app step for that bench

#### Scenario: Bench missing on a terminal
- **WHEN** the user runs `fcm bench-deploy` in a terminal with no bench and no `--team`
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
- **WHEN** the user runs `fcm bench-deploy --team acme` with no bench
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
- **THEN** the system prints the running deploy state, suggests `fcm bench-show <bench>`, and exits with code 2

### Requirement: Typed confirmation
In interactive mode, the system SHALL start the deploy only after the user types the bench title exactly. Any other input SHALL cancel the deploy with exit code 2 and no write. In non-interactive mode, the system SHALL start the deploy only when `--confirm` equals the bench FC name. The system SHALL NOT provide a `--yes` option for a deploy.

#### Scenario: Correct title typed
- **WHEN** the user types the bench title exactly
- **THEN** the system sends the deploy request

#### Scenario: Wrong text typed
- **WHEN** the user types anything else, or presses Enter on an empty line
- **THEN** the system prints that the deploy was cancelled, sends no write request, and exits with code 2

#### Scenario: Script without confirm
- **WHEN** a script runs `fcm bench-deploy bench-1234 --all-apps --json` with no `--confirm`
- **THEN** the system exits with code 2, sends no write request, and the error says that `--confirm bench-1234` is required

#### Scenario: Script with wrong confirm
- **WHEN** a script passes `--confirm bench-9999` for bench `bench-1234`
- **THEN** the system exits with code 2 and sends no write request

### Requirement: Dry run
The system SHALL accept `--dry-run`. With `--dry-run`, the system SHALL run the walk and show the preview, and SHALL NOT ask for confirmation or send any write request.

#### Scenario: Dry run
- **WHEN** the user runs `fcm bench-deploy bench-1234 --all-apps --dry-run`
- **THEN** the system prints the preview, exits with code 0, and sends no write request

### Requirement: Deploy progress
After FC accepts the deploy, the system SHALL follow the deploy until it reaches a final state, and SHALL show the current state and the build steps as they change. The system SHALL poll FC no more often than every 2 seconds. Ctrl+C SHALL stop the watch only: the system SHALL say that the deploy continues on FC and suggest `fcm bench-show <bench>`. The system SHALL accept `--no-wait` to return right after FC accepts the deploy.

#### Scenario: Watch to the end
- **WHEN** FC accepts the deploy
- **THEN** the system shows each build step and its state until the deploy succeeds or fails

#### Scenario: Ctrl+C during the watch
- **WHEN** the user presses Ctrl+C while the system follows the deploy
- **THEN** the system prints that the deploy continues on FC, names `fcm bench-show <bench>`, and sends no cancel request to FC

### Requirement: Bench detail
The system SHALL provide `fcm bench-show [BENCH]`. With no BENCH on a terminal, it SHALL use the same team-then-bench walk as `fcm bench-deploy`. It SHALL show the team, the bench title and name, the Frappe version, the status, each app with its current version and any available update, the sites on the bench, and the state of a running deploy with its build steps. `fcm bench-show` SHALL NOT change any state on FC.

#### Scenario: Bench with a running deploy
- **WHEN** the user runs `fcm bench-show bench-1234` while a deploy runs
- **THEN** the system shows the deploy state and the current build step

#### Scenario: Bench detail as JSON
- **WHEN** the user runs `fcm bench-show bench-1234 --json`
- **THEN** stdout is one JSON object with the bench, its apps with update fields, its sites, and the deploy state
