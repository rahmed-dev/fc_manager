# Spec Delta

## Purpose

Defines how the tool talks to the Frappe Cloud API: authentication, team selection, transport safety, the read-only boundary, secret redaction, and error mapping.

## ADDED Requirements

### Requirement: Authenticated requests
The system SHALL send `Authorization: Token <api-key>:<api-secret>` on every FC API request. When a request is for one team, the system SHALL also send `X-Press-Team: <team>`.

#### Scenario: Team-scoped request
- **WHEN** the system lists benches for team `acme`
- **THEN** the request carries the `Authorization` header and `X-Press-Team: acme`

### Requirement: HTTPS only
The system SHALL send requests over HTTPS only. The system SHALL reject a profile base URL that does not start with `https://`. The system SHALL keep TLS certificate verification on.

#### Scenario: Plain HTTP base URL
- **WHEN** the user adds a profile with `--base-url http://example.com`
- **THEN** the system refuses the profile with an error

### Requirement: Read-only method allowlist
The system SHALL call only the FC API methods on a fixed read-only allowlist. A call to any other method SHALL fail inside the tool before any network request.

#### Scenario: Method not on the allowlist
- **WHEN** code asks the API client to call a method that is not on the allowlist
- **THEN** the client raises an error and sends no request

### Requirement: Secret redaction
The system SHALL NOT write the API secret, the API key, or the `Authorization` header value to any output. This includes normal output, error messages, debug output, and log files.

#### Scenario: Debug output
- **WHEN** the user runs any command with `--debug`
- **THEN** the request headers in the output show `Authorization` as redacted

#### Scenario: Unexpected exception
- **WHEN** an unexpected exception occurs during a request
- **THEN** the error text and any traceback contain neither the key nor the secret

### Requirement: Error mapping
The system SHALL map each FC failure to one tool error kind: authentication, permission, not found, validation, rate limit, server, or network. The system SHALL show the FC server message when FC gives one.

#### Scenario: Permission denied in a team
- **WHEN** FC returns a permission error for a request in team `client-x`
- **THEN** the system reports a permission error that names team `client-x` and shows the FC message

#### Scenario: Network failure
- **WHEN** the FC host is not reachable or the request times out
- **THEN** the system reports a network error that names the host

### Requirement: Bounded retries and timeouts
The system SHALL apply a timeout to every request. The system SHALL retry a read request at most 2 times after a network error or a server error (HTTP 5xx). The system SHALL NOT retry after an authentication, permission, not-found, or validation error.

#### Scenario: Server error then success
- **WHEN** the first request returns HTTP 502 and the retry succeeds
- **THEN** the command succeeds

#### Scenario: Authentication error
- **WHEN** FC returns an authentication error
- **THEN** the system sends no retry
