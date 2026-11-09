# Spec Delta

## Purpose

Adds the first write verb and the exit code for a deploy that FC accepted but that failed.

## MODIFIED Requirements

### Requirement: Fixed verb set
The system SHALL use only these verbs for commands that do not change FC: `list` (many items), `show` (one item in detail), `add` and `remove` (local profiles only), and `test` (credential check). A new read command SHALL reuse one of these verbs. The system SHALL use only the verb `deploy` for a command that changes FC. Every command with a verb that changes FC SHALL show a preview and require a typed confirmation before its first write request.

#### Scenario: Detail of one item
- **WHEN** the user wants the details of one site
- **THEN** the command is `fcm site show <name>`

#### Scenario: Write verb
- **WHEN** the user wants to deploy app updates to a bench
- **THEN** the command is `fcm bench deploy <bench>`, and it shows a preview and asks for a typed confirmation before it changes FC

### Requirement: Stable exit codes
The system SHALL exit with these codes: 0 success, 1 unexpected error, 2 usage or configuration error, 3 authentication error, 4 permission error, 5 not found, 6 network or server error, 7 partial failure across teams, 8 an FC job that FC accepted but that failed.

#### Scenario: Not found
- **WHEN** `fcm site show missing.example.com` finds no site
- **THEN** the exit code is 5

#### Scenario: Partial failure
- **WHEN** a list over several teams succeeds for some teams and fails for one
- **THEN** the exit code is 7

#### Scenario: Deploy failed on FC
- **WHEN** FC accepts a deploy and the build then fails
- **THEN** the exit code is 8
