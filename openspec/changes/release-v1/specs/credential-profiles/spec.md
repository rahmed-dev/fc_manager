# Spec Delta

## MODIFIED Requirements

### Requirement: Add a profile
The system SHALL let the user add a named profile. A profile holds one FC API key and one FC API secret. The system SHALL read the secret from a prompt, never from a command-line argument. The prompt SHALL show the typed secret, so the user can check a paste. After the prompt, the system SHALL NOT show the secret in any output. The system SHALL verify the credentials against FC before it stores them.

#### Scenario: Valid credentials
- **WHEN** the user runs `fcm profile-add work` and enters a valid key and secret
- **THEN** the system calls FC to verify them, stores them, and prints the FC user email and the number of teams found

#### Scenario: Invalid credentials
- **WHEN** the user enters a key or secret that FC rejects
- **THEN** the system stores nothing and prints an authentication error with a hint to make a new key in the FC dashboard

#### Scenario: Secret is not echoed
- **WHEN** the user pastes the secret at the prompt
- **THEN** the prompt line shows the pasted secret, and no later output of the system echoes it

#### Scenario: Duplicate name
- **WHEN** the user adds a profile with a name that already exists
- **THEN** the system refuses, unless the user passes `--replace`

## ADDED Requirements

### Requirement: First-run setup
When the user runs `fcm` with no command on a terminal, and no profile exists, no profile is selected, and no environment credentials are set, the system SHALL start a setup step before the menu. Outside a terminal, the system SHALL NOT start the setup step.

#### Scenario: First run on a terminal
- **WHEN** a new user runs `fcm` on a terminal with no profile and no `FCM_API_KEY`
- **THEN** the system starts the setup step before the menu

### Requirement: First-run setup steps
The setup step SHALL ask for a profile name (default `default`), the API key, and the API secret. It SHALL check the credentials with FC, store them as `fcm profile-add` does, make the profile the default, and then open the menu.

#### Scenario: Setup saves the profile
- **WHEN** the user completes the setup step with a valid key
- **THEN** the system asks for the profile name, the API key and the secret, checks them with FC, saves the profile, says which FC user it found, and opens the menu

#### Scenario: Rejected credentials
- **WHEN** FC rejects the key or the secret in the setup step
- **THEN** the system stores nothing, shows the authentication error with the hint to run `fcm` again to retry the setup, and exits with code 3

#### Scenario: No keyring
- **WHEN** the host has no secure OS keyring at the first run
- **THEN** the system asks for nothing, says that no keyring is available, tells the user to set `FCM_API_KEY` and `FCM_API_SECRET`, and exits with code 2

#### Scenario: Environment credentials set
- **WHEN** `FCM_API_KEY` and `FCM_API_SECRET` are set and no profile exists
- **THEN** the system starts no setup step and opens the menu with the environment credentials

#### Scenario: Not a terminal
- **WHEN** a script runs `fcm` with no command, no profile and no environment credentials
- **THEN** the system prints the help and asks for nothing

### Requirement: Key format check
When the user adds a profile, in `fcm profile-add` or in the first-run setup, the system SHALL refuse an API key or an API secret that holds a space or a `:`, before any FC request. The error SHALL NOT show the typed value.

#### Scenario: Pasted label
- **WHEN** the user pastes `Key: <key> Secret: <secret>` at the API key prompt
- **THEN** the system says that the value does not look like an FC API key, sends no request to FC, stores nothing, shows neither value, and exits with code 2
