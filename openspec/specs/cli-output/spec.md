# cli-output Specification

## Purpose

Defines the shape of every `fcm` command and what the user sees from it: one command grammar, formatted results, machine-readable output, clear errors, stable exit codes, and opt-in debug detail.

## Requirements

### Requirement: Noun-verb command grammar
Every command SHALL have the form `fcm <noun> <verb> [TARGET] [options]`. The noun SHALL be a singular resource type: `profile`, `team`, `bench`, or `site`. The system SHALL NOT provide plural or alias forms of a command.

#### Scenario: Singular noun
- **WHEN** the user runs `fcm site list`
- **THEN** the system lists sites

#### Scenario: Plural form
- **WHEN** the user runs `fcm sites`
- **THEN** the system exits with code 2 and suggests `fcm site list`

### Requirement: Fixed verb set
The system SHALL use only these verbs for commands that do not change FC: `list` (many items), `show` (one item in detail), `add` and `remove` (local profiles only), and `test` (credential check). A new read command SHALL reuse one of these verbs.

#### Scenario: Detail of one item
- **WHEN** the user wants the details of one site
- **THEN** the command is `fcm site show <name>`

### Requirement: Positional target
When a command acts on one item, the item SHALL be the one positional argument, and it SHALL identify an item of the command's noun. A command SHALL NOT take its main target as an option. The positional argument MAY be left out only where the interactive picker applies.

#### Scenario: Target is positional
- **WHEN** the user runs `fcm profile test work`
- **THEN** the system tests the profile named `work`

### Requirement: Interactive picker for a missing or ambiguous target
In interactive mode, when a required target is missing or matches more than one item, the system SHALL show a fuzzy-search picker. The picker SHALL list items from all teams in scope, and each entry SHALL show the item name with its team label and bench title.

#### Scenario: Missing site on a terminal
- **WHEN** the user runs `fcm site show` in a terminal with no site name
- **THEN** the system shows a picker of all sites in all discovered teams, and shows the details of the site that the user picks

#### Scenario: Ambiguous title on a terminal
- **WHEN** the user runs `fcm site list --bench "Prod"` in a terminal and 2 benches have the title `Prod`
- **THEN** the system shows a picker with the 2 benches and their team titles

#### Scenario: Picker cancelled
- **WHEN** the user cancels the picker
- **THEN** the system exits with code 2 and does nothing else

### Requirement: No prompts in non-interactive mode
The system SHALL be in interactive mode only when stdin and stdout are both terminals and `--json` is not set. In non-interactive mode, the system SHALL NOT prompt. A missing target SHALL exit with code 2. An ambiguous target SHALL exit with code 2 and list the candidates with name, title, and team.

#### Scenario: Missing target in a script
- **WHEN** a script runs `fcm site show --json` with no site name
- **THEN** the system exits with code 2 and writes a JSON error to stderr

#### Scenario: Ambiguous target in a pipe
- **WHEN** `fcm site list --bench "Prod"` runs with stdout piped and 2 benches match
- **THEN** the system exits with code 2 and the error lists both benches with their names and teams

### Requirement: Options only narrow or modify
Options SHALL only narrow a result (for example `--bench`, `--status`) or modify behavior. The options `--profile`, `--team`, `--json`, and `--debug` SHALL have the same meaning on every command that accepts them.

#### Scenario: Same option, same meaning
- **WHEN** the user passes `--team acme` to `fcm bench list` and to `fcm site list`
- **THEN** both commands limit the result to team `acme`

### Requirement: Formatted output on a terminal
When stdout is a terminal, the system SHALL show results as aligned tables with column headers. Each list SHALL end with a one-line summary of the row count and the teams covered.

#### Scenario: Site list on a terminal
- **WHEN** the user runs `fcm site list` in a terminal
- **THEN** the system prints a table with headers and a summary line such as `12 sites in 3 teams`

#### Scenario: Empty result
- **WHEN** a list has no rows
- **THEN** the system prints a plain message such as `No sites found in team acme`, not an empty table

### Requirement: JSON output
Every command that shows data SHALL accept `--json`. With `--json`, the system SHALL write only valid JSON to stdout, and SHALL write errors as JSON to stderr.

#### Scenario: JSON list
- **WHEN** the user runs `fcm bench list --json`
- **THEN** stdout is one JSON array of bench objects and contains no other text

#### Scenario: JSON error
- **WHEN** a command run with `--json` fails
- **THEN** stderr holds one JSON object with the keys `error`, `kind`, and `hint`

### Requirement: Clear error messages
Each error SHALL show what failed, the target (profile, team, bench, or site) when known, the FC server message when known, and a hint for the next step. The system SHALL NOT show a Python traceback unless `--debug` is set.

#### Scenario: Authentication error
- **WHEN** FC rejects the credentials of profile `work`
- **THEN** the system prints one error that names profile `work`, says the credentials were rejected, and gives the hint `fcm profile add work --replace`

#### Scenario: Permission error names the team owner
- **WHEN** FC denies a call in a team whose owner email is `owner@acme.example.com`
- **THEN** the hint says to ask `owner@acme.example.com` for access, and does not tell the user to leave the team out with `--team` for a single-item command

### Requirement: Stable exit codes
The system SHALL exit with these codes: 0 success, 1 unexpected error, 2 usage or configuration error, 3 authentication error, 4 permission error, 5 not found, 6 network or server error, 7 partial failure across teams.

#### Scenario: Not found
- **WHEN** `fcm site show missing.example.com` finds no site
- **THEN** the exit code is 5

#### Scenario: Partial failure
- **WHEN** a list over several teams succeeds for some teams and fails for one
- **THEN** the exit code is 7

### Requirement: Debug output
The system SHALL accept `--debug`. With `--debug`, the system SHALL write each request method name, team, HTTP status, and duration to stderr, and SHALL show the traceback for unexpected errors, with secrets redacted.

#### Scenario: Debug a request
- **WHEN** the user runs `fcm team list --debug`
- **THEN** stderr shows each FC method called, its HTTP status, and its duration, and no secret value

### Requirement: Color control
The system SHALL turn off color when stdout is not a terminal or when `NO_COLOR` is set.

#### Scenario: Piped output
- **WHEN** the user pipes `fcm site list` to another program
- **THEN** the output contains no color escape codes
