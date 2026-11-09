# Spec Delta

## ADDED Requirements

### Requirement: Version option
The system SHALL provide `fcm --version`. It SHALL print `fcm` and the installed version, and exit with code 0. It SHALL read no credentials and send no request to FC.

#### Scenario: Version
- **WHEN** the user runs `fcm --version` with version 1.0.0 installed
- **THEN** the system prints `fcm 1.0.0` and exits with code 0, with no FC request
