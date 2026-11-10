# credential-profiles Specification

## Purpose

Lets a user store, select, and check Frappe Cloud credentials for one or more FC logins, without a secret ever touching a plain file or the terminal output.

## Requirements

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

### Requirement: Environment-variable credentials
The system SHALL accept credentials from the environment variables `FCM_API_KEY` and `FCM_API_SECRET`. When both are set, they SHALL take precedence over the keyring for that run.

#### Scenario: CI run with environment variables
- **WHEN** both `FCM_API_KEY` and `FCM_API_SECRET` are set and the user runs a list command
- **THEN** the system uses those credentials and does not read the keyring

#### Scenario: Only one variable set
- **WHEN** only one of the two variables is set
- **THEN** the system stops with a configuration error that names the missing variable

### Requirement: Select the active profile
The system SHALL use the profile named by `--profile`, else the profile named by `FCM_PROFILE`, else the default profile in the config. The first profile added SHALL become the default.

#### Scenario: Explicit profile
- **WHEN** the user passes `--profile client`
- **THEN** the system uses the `client` profile for that run

#### Scenario: No profile configured
- **WHEN** no profile exists and no credential environment variables are set
- **THEN** the system stops with an error that tells the user to run `fcm profile-add`

### Requirement: List profiles
The system SHALL list profile names, the default marker, the base URL, and the store (`keyring` or `file`). It SHALL NOT show any part of the key or the secret.

#### Scenario: List
- **WHEN** the user runs `fcm profile-list`
- **THEN** the system shows each profile name, marks the default, and shows the store, with no credential characters

### Requirement: Test a profile
The system SHALL let the user test a stored profile against FC and report the result.

#### Scenario: Test passes
- **WHEN** the user runs `fcm profile-test work` and FC accepts the credentials
- **THEN** the system prints the FC user and the teams it can reach

#### Scenario: Revoked key
- **WHEN** FC rejects the stored credentials
- **THEN** the system prints an authentication error and a hint to replace the key with `fcm profile-add work --replace`

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
- **WHEN** the host has no working OS keyring at the first run
- **THEN** the system asks for the profile name, the key and the secret, checks them with FC, says why the keyring does not work, and asks the file question; on yes it saves the profile and opens the menu, on no it saves nothing and exits with code 2

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

### Requirement: Replace moves the store
When `fcm profile-add <name> --replace` saves the key in a store that differs from the old store of the profile, the system SHALL remove the old entry from the old store. A failure to remove the old keyring entry SHALL NOT stop the save.

#### Scenario: From file to keyring
- **WHEN** the user replaces a file profile on a host where the keyring works
- **THEN** the key is in the keyring, the profile store is `keyring`, and the credentials file has no entry for the profile
