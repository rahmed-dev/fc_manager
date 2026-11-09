# Spec Delta

## Purpose
Lets a user install one app on one Frappe Cloud site from `fcm`, with a clear target, a preview, a typed confirmation, and a live view of the FC install job until it ends. The app must already be on the bench of the site.

## ADDED Requirements

### Requirement: Install-app command
The system SHALL provide `fcm site-install-app [SITE]`. It SHALL send one FC request that installs one app on one site. SITE SHALL be resolved as for `site-show`. With no SITE in interactive mode, the system SHALL ask for the team, then the bench, then a site of that bench. With no SITE in non-interactive mode, the system SHALL exit with code 2 and send nothing.

#### Scenario: Site given
- **WHEN** the user runs `fcm site-install-app erp.acme.example.com`
- **THEN** the system runs the checks for that site and then shows the app step

#### Scenario: No site in a script
- **WHEN** a script runs `fcm site-install-app --json` with no SITE
- **THEN** the system exits with code 2 and sends no request to FC

### Requirement: Install checks
Before the app step, the system SHALL read the site status and the FC jobs in progress for the site. The system SHALL refuse the install, with exit code 2 and no write, when the site status is not Active. The system SHALL also refuse it when FC has a job in Pending or Running state for the site. The error SHALL name the status or the job.

#### Scenario: Site not active
- **WHEN** the site status on FC is `Inactive`
- **THEN** the system says that FC installs an app only on an Active site, sends no write request, and exits with code 2

#### Scenario: Job in progress
- **WHEN** FC has a `Backup Site` job in the Running state for the site
- **THEN** the system names the running job, sends no write request, and exits with code 2

### Requirement: App step for a site
The system SHALL read the apps that FC offers for the site: the apps on the bench of the site that the site does not have. The app step SHALL show each app with its title, app name and branch. When no app is offered, the system SHALL say that every app of the bench is already on the site, and exit with code 0.

#### Scenario: Apps listed
- **WHEN** the bench of site `erp.acme.example.com` has app `crm` and the site does not have it
- **THEN** the app step lists `crm` with its title and branch

#### Scenario: Nothing to install
- **WHEN** the site has every app of its bench
- **THEN** the system says so, sends no write request, and exits with code 0

### Requirement: Apps with plans
An app for which FC returns marketplace plans SHALL be shown as "has plans: install it from the FC dashboard", and the user SHALL NOT be able to pick it. The system SHALL NOT send a plan to FC. With `--app` set to such an app, the system SHALL exit with code 2, say to install the app from the FC dashboard, and send no write request.

#### Scenario: App with plans in the list
- **WHEN** FC returns plans for app `helpdesk` on the site
- **THEN** the app step shows `helpdesk` with "has plans: install it from the FC dashboard", and the user cannot pick it

#### Scenario: App with plans given
- **WHEN** the user runs `fcm site-install-app erp.acme.example.com --app helpdesk` and FC returns plans for `helpdesk`
- **THEN** the system says to install `helpdesk` from the FC dashboard, sends no write request, and exits with code 2

### Requirement: App option for a site
With `--app <app>`, the system SHALL pick that app by its app name and SHALL show no app step. When FC does not offer the app for the site, the system SHALL exit with code 2, name the app, and send no write request. With no `--app` in non-interactive mode, the system SHALL exit with code 2 and send no write request.

#### Scenario: App not offered
- **WHEN** the user runs `fcm site-install-app erp.acme.example.com --app crm` and the bench of the site does not have `crm`
- **THEN** the system says that `crm` is not on the bench or is already on the site, names `fcm bench-add-app`, sends no write request, and exits with code 2

### Requirement: Install preview
Before the confirmation, the system SHALL show a preview with: the profile, the team label and team name, the team owner email, the bench title and bench name, the site name, the site status, and the app title, app name and branch. The preview SHALL say that FC runs the install on the live site. The preview SHALL be the last output before the confirmation prompt.

#### Scenario: Preview content
- **WHEN** the user reaches the confirmation for app `crm` on site `erp.acme.example.com`
- **THEN** the preview shows the profile, the team with its owner, the bench, the site with its status, and the app with its branch

### Requirement: Install confirmation
In interactive mode, the system SHALL send the install only after the user types the site name exactly. Any other input SHALL cancel the install with exit code 2 and no write. In non-interactive mode, the system SHALL send the install only when `--confirm` equals the site name. The system SHALL NOT provide a `--yes` option.

#### Scenario: Correct name typed
- **WHEN** the user types `erp.acme.example.com` at the confirmation for that site
- **THEN** the system sends the install request

#### Scenario: Wrong text typed
- **WHEN** the user types anything else, or presses Enter on an empty line
- **THEN** the system prints that the install was cancelled, sends no write request, and exits with code 2

#### Scenario: Script without confirm
- **WHEN** a script runs `fcm site-install-app erp.acme.example.com --app crm --json` with no `--confirm`
- **THEN** the system exits with code 2, sends no write request, and the error says that `--confirm erp.acme.example.com` is required

### Requirement: Install dry run
With `--dry-run`, the system SHALL run the checks, pick the app and show the preview, and then exit with code 0. It SHALL send no write request and SHALL NOT ask for a confirmation.

#### Scenario: Dry run
- **WHEN** the user runs `fcm site-install-app erp.acme.example.com --app crm --dry-run`
- **THEN** the system shows the preview, says that nothing was sent, sends no write request, and exits with code 0

### Requirement: Install request
The system SHALL send the install as one POST to `press.api.site.install_app` with the team header, the site name and the app name, and with no plan. The system SHALL NOT retry it. When FC does not confirm the request, the system SHALL say that the install state on FC is not known, name `fcm site-show <site>`, and exit with code 6.

#### Scenario: Request body
- **WHEN** the user confirms the install of app `crm` on site `erp.acme.example.com` in team `acme`
- **THEN** the request is a POST to `press.api.site.install_app` with `X-Press-Team: acme` and a JSON body with `name` `erp.acme.example.com` and `app` `crm`, and no `plan`

#### Scenario: Request times out
- **WHEN** the install request times out
- **THEN** the system sends no second request, says that the install state on FC is not known, names `fcm site-show erp.acme.example.com`, and exits with code 6

### Requirement: Install job watch
After FC accepts the request, the system SHALL find the new FC "Install App on Site" job of the site and show its steps as they change, until the job ends. The watch SHALL show the same liveness line as the migrate watch. With `--no-wait`, the system SHALL exit with code 0 after FC accepts the request. Ctrl+C SHALL stop the watch only: the system SHALL say that the install continues on FC and exit with code 130.

#### Scenario: No wait
- **WHEN** the user runs the install with `--no-wait` and FC accepts it
- **THEN** the system says that the install started, names `fcm site-show <site>`, and exits with code 0

#### Scenario: Watch stopped
- **WHEN** the user presses Ctrl+C during the watch
- **THEN** the system says that the install continues on FC, sends no request to stop it, and exits with code 130

### Requirement: Install result
When the job ends in Success, the system SHALL say that the app is installed on the site and exit with code 0. When the job ends in Failure, the system SHALL name the failed step and exit with code 8. When the system cannot find the new job within 2 minutes after FC accepts the request, it SHALL say that the result is not known, name `fcm site-show <site>`, and exit with code 6.

#### Scenario: Success
- **WHEN** the install job ends in Success
- **THEN** the system says that the app is installed on the site and exits with code 0

#### Scenario: Failure
- **WHEN** the install job ends in Failure at the step "Install App on Site"
- **THEN** the system names that step as failed and exits with code 8

#### Scenario: Job not found
- **WHEN** no new install job appears for the site within 2 minutes after FC accepts the request
- **THEN** the system says that the result is not known, names `fcm site-show <site>`, and exits with code 6
