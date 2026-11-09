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

#### Scenario: Add-app write request times out
- **WHEN** an add-app write request for bench `bench-1234` times out or returns HTTP 502
- **THEN** the system sends no second write request, and the error says that the app state on FC is not known and names `fcm bench-show bench-1234`

#### Scenario: Install write request times out
- **WHEN** an install write request for site `erp.acme.example.com` times out or returns HTTP 502
- **THEN** the system sends no second write request, and the error says that the install state on FC is not known and names `fcm site-show erp.acme.example.com`

### Requirement: Write method allowlist
The write allowlist SHALL hold only `press.api.bench.deploy_and_update`, `press.api.site.migrate`, `press.api.site.update`, `press.api.bench.add_apps`, `press.api.client.run_doc_method` and `press.api.site.install_app`. The system SHALL send a write call as an HTTP POST with a JSON body and the team header. `bench-add-app` SHALL own `add_apps` and `run_doc_method`; each other write method SHALL belong to the command of the same name.

#### Scenario: Deploy request
- **WHEN** the deploy command sends the deploy for bench `bench-1234` in team `acme`
- **THEN** the request is a POST to `press.api.bench.deploy_and_update` with `X-Press-Team: acme` and a JSON body that names the bench, the apps, and the sites

#### Scenario: Migrate request
- **WHEN** the migrate command sends the migrate for site `erp.acme.example.com` in team `acme`
- **THEN** the request is a POST to `press.api.site.migrate` with `X-Press-Team: acme` and a JSON body that names the site and the failing-patch mode

#### Scenario: Update request
- **WHEN** the update command sends the update for site `erp.acme.example.com` in team `acme`
- **THEN** the request is a POST to `press.api.site.update` with `X-Press-Team: acme` and a JSON body that names the site, the failing-patch mode, and `skip_backups` false

#### Scenario: Marketplace add request
- **WHEN** the add-app command sends the add of app `crm` for bench `bench-1234` in team `acme`
- **THEN** the request is a POST to `press.api.bench.add_apps` with `X-Press-Team: acme` and a JSON body that names the bench and a list of apps with their sources

#### Scenario: Install request
- **WHEN** the install command sends the install of app `crm` for site `erp.acme.example.com` in team `acme`
- **THEN** the request is a POST to `press.api.site.install_app` with `X-Press-Team: acme` and a JSON body that names the site and the app

#### Scenario: Read command
- **WHEN** the user runs any `list` or `show` command
- **THEN** the system sends no POST request

#### Scenario: Each command sends only its own write
- **WHEN** the user runs `fcm bench-deploy`, `fcm site-migrate`, `fcm site-update`, `fcm bench-add-app` or `fcm site-install-app`, not as a dry run
- **THEN** each command sends only its own write method: `deploy_and_update`, `migrate`, `update`, `add_apps` or `run_doc_method`, or `install_app`

## ADDED Requirements

### Requirement: Document method write
The system SHALL send `press.api.client.run_doc_method` only with the doctype `Release Group` and the method `add_app`. Any other doctype or method SHALL raise an error in the client and send no request.

#### Scenario: Other doc method
- **WHEN** code asks the client to write `run_doc_method` with the doctype `Site` or the method `archive`
- **THEN** the client raises an error and sends no request

### Requirement: GitHub reads
The read allowlist SHALL include `press.api.github.options`, `press.api.github.branches` and `press.api.github.app`, so that the add-app command can list the GitHub repositories of the team, the branches of a repository, and the app name and Frappe version range of a branch.

#### Scenario: App of a branch
- **WHEN** the add-app command reads the app of branch `main` of `acme/tools`
- **THEN** the request is a GET to `press.api.github.app` with `owner` `acme`, `repository` `tools` and `branch` `main`

### Requirement: App list reads
The read allowlist SHALL include `press.api.bench.all_apps` and `press.api.site.available_apps`. The add-app command SHALL read the apps that FC offers for one bench group through `all_apps`. The install command SHALL read the apps that FC offers for one site through `available_apps`. Both reads SHALL take a plain name.

#### Scenario: Apps for a bench group
- **WHEN** the add-app command reads the apps for bench `bench-1234`
- **THEN** the request is a GET to `press.api.bench.all_apps` with the name `bench-1234`

#### Scenario: Apps for a site
- **WHEN** the install command reads the apps for site `erp.acme.example.com`
- **THEN** the request is a GET to `press.api.site.available_apps` with the name `erp.acme.example.com`
