# Spec Delta

## MODIFIED Requirements

### Requirement: Secrets stored only in the OS keyring
The system SHALL store the API key and the API secret in the OS keyring only. The config file SHALL hold profile names and non-secret settings only. The system SHALL NOT fall back to a plain-text secret file.

#### Scenario: Config file has no secrets
- **WHEN** a profile is added
- **THEN** the config file contains the profile name and base URL, and contains neither the key nor the secret

#### Scenario: No keyring available
- **WHEN** the user adds a profile on a host with no usable keyring backend
- **THEN** the system stores nothing and prints an error that names the environment-variable fallback

#### Scenario: Keyring daemon runs but cannot open a keyring
- **WHEN** the user runs `fcm profile-add work` on a host where a keyring service runs, but a read from it fails (for example, no default keyring exists and the service cannot prompt for one)
- **THEN** the system asks for no key and no secret, stores nothing, prints an error that names the environment-variable fallback, and exits with code 2

### Requirement: First-run setup steps
The setup step SHALL ask for a profile name (default `default`), the API key, and the API secret. It SHALL check the credentials with FC, store them as `fcm profile-add` does, make the profile the default, and then open the menu.

#### Scenario: Setup saves the profile
- **WHEN** the user completes the setup step with a valid key
- **THEN** the system asks for the profile name, the API key and the secret, checks them with FC, saves the profile, says which FC user it found, and opens the menu

#### Scenario: Rejected credentials
- **WHEN** FC rejects the key or the secret in the setup step
- **THEN** the system stores nothing, shows the authentication error with the hint to run `fcm` again to retry the setup, and exits with code 3

#### Scenario: No keyring
- **WHEN** the host has no secure OS keyring at the first run, or the keyring service runs but a read from it fails
- **THEN** the system asks for nothing, says that no keyring is available and why, tells the user to set `FCM_API_KEY` and `FCM_API_SECRET`, and exits with code 2

#### Scenario: Environment credentials set
- **WHEN** `FCM_API_KEY` and `FCM_API_SECRET` are set and no profile exists
- **THEN** the system starts no setup step and opens the menu with the environment credentials

#### Scenario: Not a terminal
- **WHEN** a script runs `fcm` with no command, no profile and no environment credentials
- **THEN** the system prints the help and asks for nothing

## ADDED Requirements

### Requirement: Keyring check before any prompt
Before the system asks for an API key, it SHALL check that the keyring works with a real read of an entry that holds no secret. A keyring that raises an error on that read SHALL count as not usable. The check SHALL NOT write to the keyring.

#### Scenario: Read fails
- **WHEN** the keyring service raises an error on the check read
- **THEN** the system treats the host as a host with no keyring and asks for no key

#### Scenario: Read works
- **WHEN** the check read returns with no error (an empty result is a success)
- **THEN** the system continues to the key prompt

#### Scenario: Check writes nothing
- **WHEN** the system runs the check
- **THEN** the keyring holds no new entry after the check

### Requirement: Plain cause in keyring errors
When the keyring fails, the error SHALL say the cause in plain words, not only an exception class name. It SHALL name `FCM_API_KEY` and `FCM_API_SECRET` as the fallback. On Linux it SHALL point to the README section on a keyring for a headless host. The error SHALL NOT show any key or secret.

#### Scenario: No default keyring on Linux
- **WHEN** the keyring service has no default keyring and cannot prompt for one
- **THEN** the error says that the keyring cannot open its default keyring on this host, and the hint names `FCM_API_KEY`, `FCM_API_SECRET` and the README section

#### Scenario: Locked keyring
- **WHEN** the keyring is locked and the read or write fails for that reason
- **THEN** the error says that the keyring is locked, and the hint names the environment-variable fallback

#### Scenario: Read of a stored profile fails
- **WHEN** a command loads a stored profile and the keyring read fails
- **THEN** the system stops with code 2 and the same plain cause and hint
