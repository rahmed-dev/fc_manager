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
- **WHEN** a deploy write request times out or returns HTTP 502
- **THEN** the system sends no second write request, and the error says that the deploy state on FC is not known and names `fcm bench-show <bench>`

#### Scenario: Migrate write request times out
- **WHEN** a migrate write request for site `erp.acme.example.com` times out or returns HTTP 502
- **THEN** the system sends no second write request, and the error says that the migrate state on FC is not known and names `fcm site-show erp.acme.example.com`

### Requirement: Write method allowlist
The write allowlist SHALL hold only `press.api.bench.deploy_and_update` and `press.api.site.migrate`. The system SHALL send a write call as an HTTP POST with a JSON body and the team header. Each write method SHALL belong to one command: `press.api.bench.deploy_and_update` to `bench-deploy`, and `press.api.site.migrate` to `site-migrate`. No other command SHALL use the write path.

#### Scenario: Deploy request
- **WHEN** the deploy command sends the deploy for bench `bench-1234` in team `acme`
- **THEN** the request is a POST to `press.api.bench.deploy_and_update` with `X-Press-Team: acme` and a JSON body that names the bench, the apps, and the sites

#### Scenario: Migrate request
- **WHEN** the migrate command sends the migrate for site `erp.acme.example.com` in team `acme`
- **THEN** the request is a POST to `press.api.site.migrate` with `X-Press-Team: acme` and a JSON body that names the site and the failing-patch mode

#### Scenario: Read command
- **WHEN** the user runs any `list` or `show` command
- **THEN** the system sends no POST request

#### Scenario: Each command sends only its own write
- **WHEN** the user runs `fcm bench-deploy` or `fcm site-migrate`, not as a dry run
- **THEN** the deploy command sends only `press.api.bench.deploy_and_update`, and the migrate command sends only `press.api.site.migrate`

## ADDED Requirements

### Requirement: Site job reads
The read allowlist SHALL include `press.api.site.running_jobs` and `press.api.site.job`, so that the migrate command can find and follow the FC job of one site. The read allowlist SHALL NOT include a job list read that takes a filter (`press.api.site.jobs`, `press.api.client.get_list`): FC fails on its filter over GET.

#### Scenario: Running jobs of one site
- **WHEN** the migrate command reads the running jobs of site `erp.acme.example.com`
- **THEN** the request is a GET to `press.api.site.running_jobs` with the name `erp.acme.example.com`

#### Scenario: Job list read
- **WHEN** code asks the client for `press.api.site.jobs` or `press.api.client.get_list`
- **THEN** the client raises an error and sends no request
