# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Secrets stored only in the OS keyring`
- TO: `### Requirement: Secret storage`

- FROM: `### Requirement: Keyring check before any prompt`
- TO: `### Requirement: Keyring check before the save`

## MODIFIED Requirements

### Requirement: Secret storage
The system SHALL store the API key and the API secret in the OS keyring when the keyring works. When no keyring works, the system SHALL store them in a credentials file only after the user says yes. The file SHALL be in the config directory, with mode 0600, in a directory with mode 0700. The config file SHALL hold profile names, the store of each profile and other non-secret settings only.

#### Scenario: Config file has no secrets
- **WHEN** a profile is added
- **THEN** the config file contains the profile name, the base URL and the store, and contains neither the key nor the secret

#### Scenario: Keyring works
- **WHEN** the user adds a profile and the keyring works
- **THEN** the system stores the key and the secret in the keyring, writes no credentials file, and asks no file question

#### Scenario: No keyring, the user says yes
- **WHEN** the user adds a profile, FC accepts the key, the keyring does not work, and the user answers yes to the file question
- **THEN** the system writes the key and the secret to the credentials file with mode 0600, records the store `file` for the profile, and does not show the secret

#### Scenario: No keyring available
- **WHEN** the user adds a profile, FC accepts the key, the keyring does not work, and the user answers no or presses Enter
- **THEN** the system stores nothing, prints a hint that names `FCM_API_KEY` and `FCM_API_SECRET`, and exits with code 2

#### Scenario: Keyring daemon runs but cannot open a keyring
- **WHEN** the user runs `fcm profile-add work` on a host where a keyring service runs, but a read from it fails (for example, no default keyring exists and the service cannot prompt for one)
- **THEN** the system asks for the key and the secret, checks them with FC, says that the keyring cannot open its default keyring, and asks the file question

#### Scenario: Credentials file readable by others
- **WHEN** a command loads a file profile and the credentials file has any group or other permission bit set
- **THEN** the system refuses to read it, exits with code 2, and the hint names the `chmod 600` command for the file

#### Scenario: Old config file
- **WHEN** the config file has a profile with no store
- **THEN** the system treats the profile as a keyring profile

### Requirement: Keyring check before the save
After FC accepts the key, and before the system saves it, the system SHALL check that the keyring works with a real read of an entry that holds no secret. A keyring that raises an error on that read SHALL count as not usable. The check SHALL NOT write to the keyring.

#### Scenario: Read fails
- **WHEN** the keyring service raises an error on the check read
- **THEN** the system says why the keyring does not work, and asks the file question

#### Scenario: Read works
- **WHEN** the check read returns with no error (an empty result is a success)
- **THEN** the system saves the key in the keyring

#### Scenario: Check writes nothing
- **WHEN** the system runs the check
- **THEN** the keyring holds no new entry after the check

#### Scenario: Prompts come first
- **WHEN** the user runs `fcm profile-add work` on a host where the keyring does not work
- **THEN** the system asks for the API key and the API secret, and checks them with FC, before it says that the keyring does not work

### Requirement: First-run setup steps
The setup step SHALL ask for a profile name (default `default`), the API key, and the API secret. It SHALL check the credentials with FC, store them as `fcm profile-add` does, make the profile the default, and then open the menu.

#### Scenario: Setup saves the profile
- **WHEN** the user completes the setup step with a valid key
- **THEN** the system asks for the profile name, the API key and the secret, checks them with FC, saves the profile, says which FC user it found, and opens the menu

#### Scenario: Rejected credentials
- **WHEN** FC rejects the key or the secret in the setup step
- **THEN** the system stores nothing, shows the authentication error with the hint to run `fcm` again to retry the setup, and exits with code 3

#### Scenario: No keyring
- **WHEN** the host has no working OS keyring at the first run
- **THEN** the system asks for the profile name, the key and the secret, checks them with FC, says why the keyring does not work, and asks the file question; on yes it saves the profile and opens the menu, on no it saves nothing and exits with code 2

#### Scenario: Environment credentials set
- **WHEN** `FCM_API_KEY` and `FCM_API_SECRET` are set and no profile exists
- **THEN** the system starts no setup step and opens the menu with the environment credentials

#### Scenario: Not a terminal
- **WHEN** a script runs `fcm` with no command, no profile and no environment credentials
- **THEN** the system prints the help and asks for nothing

### Requirement: List profiles
The system SHALL list profile names, the default marker, the base URL, and the store (`keyring` or `file`). It SHALL NOT show any part of the key or the secret.

#### Scenario: List
- **WHEN** the user runs `fcm profile-list`
- **THEN** the system shows each profile name, marks the default, and shows the store, with no credential characters

### Requirement: Remove a profile
The system SHALL remove a profile from the config and delete its stored credentials from its store, after a confirmation.

#### Scenario: Remove with confirmation
- **WHEN** the user runs `fcm profile-remove work` and confirms
- **THEN** the profile and its stored credentials no longer exist

#### Scenario: Remove a file profile
- **WHEN** the user removes a file profile
- **THEN** the system deletes its entry from the credentials file, keeps the entries of other profiles, and does not read or write the keyring

#### Scenario: Remove cancelled
- **WHEN** the user does not confirm
- **THEN** nothing changes

## ADDED Requirements

### Requirement: Replace moves the store
When `fcm profile-add <name> --replace` saves the key in a store that differs from the old store of the profile, the system SHALL remove the old entry from the old store. A failure to remove the old keyring entry SHALL NOT stop the save.

#### Scenario: From file to keyring
- **WHEN** the user replaces a file profile on a host where the keyring works
- **THEN** the key is in the keyring, the profile store is `keyring`, and the credentials file has no entry for the profile
