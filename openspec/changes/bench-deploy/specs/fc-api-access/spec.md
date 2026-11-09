# Spec Delta

## Purpose

Adds a separate, minimal write path to the FC API client: a write allowlist, POST for writes, and no retry of a write.

## MODIFIED Requirements

### Requirement: Read-only method allowlist
The system SHALL call FC API methods only from 2 fixed allowlists: a read allowlist and a write allowlist. A read call SHALL accept only a method on the read allowlist. A generic document read method SHALL be on the read allowlist only for a fixed list of doctypes. A call to a method on neither allowlist, or a document read of another doctype, SHALL fail inside the tool before any network request.

#### Scenario: Method not on the allowlist
- **WHEN** code asks the API client to call a method that is on neither allowlist
- **THEN** the client raises an error and sends no request

#### Scenario: Document read of a doctype that is not listed
- **WHEN** code asks the client to read a `Site` document through the generic document read method
- **THEN** the client raises an error and sends no request

#### Scenario: Write method through the read path
- **WHEN** code asks the read path of the client to call `press.api.bench.deploy_and_update`
- **THEN** the client raises an error and sends no request

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
- **THEN** the system sends no second write request, and the error says that the deploy state on FC is not known and names `fcm bench show <bench>`

## ADDED Requirements

### Requirement: Write method allowlist
The write allowlist SHALL hold only `press.api.bench.deploy_and_update`. The system SHALL send a write call as an HTTP POST with a JSON body and the team header. Only the deploy command SHALL use the write path.

#### Scenario: Deploy request
- **WHEN** the deploy command sends the deploy for bench `bench-1234` in team `acme`
- **THEN** the request is a POST to `press.api.bench.deploy_and_update` with `X-Press-Team: acme` and a JSON body that names the bench, the apps, and the sites

#### Scenario: Read command
- **WHEN** the user runs any `list` or `show` command
- **THEN** the system sends no POST request
