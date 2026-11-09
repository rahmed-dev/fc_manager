# Spec Delta

## MODIFIED Requirements

### Requirement: Add a profile
The system SHALL let the user add a named profile. A profile holds one FC API key and one FC API secret. The system SHALL read the secret from a hidden prompt, never from a command-line argument. The system SHALL verify the credentials against FC before it stores them.

#### Scenario: Valid credentials
- **WHEN** the user runs `fcm profile-add work` and enters a valid key and secret
- **THEN** the system calls FC to verify them, stores them, and prints the FC user email and the number of teams found

#### Scenario: Invalid credentials
- **WHEN** the user enters a key or secret that FC rejects
- **THEN** the system stores nothing and prints an authentication error with a hint to make a new key in the FC dashboard

#### Scenario: Secret is not echoed
- **WHEN** the user types the secret at the prompt
- **THEN** the terminal does not show the typed characters

#### Scenario: Duplicate name
- **WHEN** the user adds a profile with a name that already exists
- **THEN** the system refuses, unless the user passes `--replace`

### Requirement: Select the active profile
The system SHALL use the profile named by `--profile`, else the profile named by `FCM_PROFILE`, else the default profile in the config. The first profile added SHALL become the default.

#### Scenario: Explicit profile
- **WHEN** the user passes `--profile client`
- **THEN** the system uses the `client` profile for that run

#### Scenario: No profile configured
- **WHEN** no profile exists and no credential environment variables are set
- **THEN** the system stops with an error that tells the user to run `fcm profile-add`

### Requirement: List profiles
The system SHALL list profile names, the default marker, and the base URL. It SHALL NOT show any part of the key or the secret.

#### Scenario: List
- **WHEN** the user runs `fcm profile-list`
- **THEN** the system shows each profile name and marks the default, with no credential characters

### Requirement: Test a profile
The system SHALL let the user test a stored profile against FC and report the result.

#### Scenario: Test passes
- **WHEN** the user runs `fcm profile-test work` and FC accepts the credentials
- **THEN** the system prints the FC user and the teams it can reach

#### Scenario: Revoked key
- **WHEN** FC rejects the stored credentials
- **THEN** the system prints an authentication error and a hint to replace the key with `fcm profile-add work --replace`

### Requirement: Remove a profile
The system SHALL remove a profile from the config and delete its keyring entries, after a confirmation.

#### Scenario: Remove with confirmation
- **WHEN** the user runs `fcm profile-remove work` and confirms
- **THEN** the profile and its keyring entries no longer exist

#### Scenario: Remove cancelled
- **WHEN** the user does not confirm
- **THEN** nothing changes
