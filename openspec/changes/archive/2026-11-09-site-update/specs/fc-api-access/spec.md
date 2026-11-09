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

#### Scenario: Update write request times out
- **WHEN** an update write request for site `erp.acme.example.com` times out or returns HTTP 502
- **THEN** the system sends no second write request, and the error says that the update state on FC is not known and names `fcm site-show erp.acme.example.com`

### Requirement: Write method allowlist
The write allowlist SHALL hold only `press.api.bench.deploy_and_update`, `press.api.site.migrate` and `press.api.site.update`. The system SHALL send a write call as an HTTP POST with a JSON body and the team header. Each write method SHALL belong to one command: `press.api.bench.deploy_and_update` to `bench-deploy`, `press.api.site.migrate` to `site-migrate`, and `press.api.site.update` to `site-update`. No other command SHALL use the write path.

#### Scenario: Deploy request
- **WHEN** the deploy command sends the deploy for bench `bench-1234` in team `acme`
- **THEN** the request is a POST to `press.api.bench.deploy_and_update` with `X-Press-Team: acme` and a JSON body that names the bench, the apps, and the sites

#### Scenario: Migrate request
- **WHEN** the migrate command sends the migrate for site `erp.acme.example.com` in team `acme`
- **THEN** the request is a POST to `press.api.site.migrate` with `X-Press-Team: acme` and a JSON body that names the site and the failing-patch mode

#### Scenario: Update request
- **WHEN** the update command sends the update for site `erp.acme.example.com` in team `acme`
- **THEN** the request is a POST to `press.api.site.update` with `X-Press-Team: acme` and a JSON body that names the site, the failing-patch mode, and `skip_backups` false

#### Scenario: Read command
- **WHEN** the user runs any `list` or `show` command
- **THEN** the system sends no POST request

#### Scenario: Each command sends only its own write
- **WHEN** the user runs `fcm bench-deploy`, `fcm site-migrate` or `fcm site-update`, not as a dry run
- **THEN** the deploy command sends only `press.api.bench.deploy_and_update`, the migrate command sends only `press.api.site.migrate`, and the update command sends only `press.api.site.update`

## ADDED Requirements

### Requirement: Site update reads
The read allowlist SHALL include `press.api.site.check_for_updates`, so that the update command can read the update info of one site. The document read method SHALL allow the doctype `Site Update`, so that the update command can read one update record by its name.

#### Scenario: Update info of one site
- **WHEN** the update command reads the update info of site `erp.acme.example.com`
- **THEN** the request is a GET to `press.api.site.check_for_updates` with the name `erp.acme.example.com`

#### Scenario: Update record read
- **WHEN** the update command reads the update record `su-0001`
- **THEN** the request is a GET to `press.api.client.get` with the doctype `Site Update` and the name `su-0001`
