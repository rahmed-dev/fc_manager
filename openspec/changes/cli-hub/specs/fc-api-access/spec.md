# Spec Delta

## MODIFIED Requirements

### Requirement: Bounded retries and timeouts
The system SHALL apply a timeout to every request. The system SHALL retry a read request at most 2 times after a network error or a server error (HTTP 5xx). The system SHALL NOT retry after an authentication, permission, not-found, or validation error. The system SHALL NOT retry a write request for any reason.

#### Scenario: Server error then success
- **WHEN** the first request returns HTTP 502 and the retry succeeds
- **THEN** the command succeeds

#### Scenario: Authentication error
- **WHEN** FC returns an authentication error
- **THEN** the system sends no retry

#### Scenario: Write request times out
- **WHEN** a write request times out or returns HTTP 502
- **THEN** the system sends no second write request, and the error says that the deploy state on FC is not known and names `fcm bench-show <bench>`
