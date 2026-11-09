# Spec Delta

## Purpose

Lets a user run `bench migrate` on one Frappe Cloud site from `fcm`, with a clear target, a preview, a typed confirmation, and a live view of the FC migrate job until it ends.

## ADDED Requirements

### Requirement: Migrate command
The system SHALL provide `fcm site-migrate [SITE]`. It SHALL send one FC migrate request for one site. SITE SHALL be the site FC name or a unique part of it, resolved as for `site-show`. With no SITE in interactive mode, the system SHALL ask for the team, then the bench, then a site of that bench. With no SITE in non-interactive mode, the system SHALL exit with code 2 and send nothing.

#### Scenario: Site given
- **WHEN** the user runs `fcm site-migrate erp.acme.example.com`
- **THEN** the system runs the checks for that site and then shows the preview

#### Scenario: No site on a terminal
- **WHEN** the user runs `fcm site-migrate` in a terminal
- **THEN** the system asks for the team, then a bench of that team, then a site of that bench

#### Scenario: No site in a script
- **WHEN** a script runs `fcm site-migrate --json` with no SITE
- **THEN** the system exits with code 2 and sends no request to FC

### Requirement: Migrate checks
Before the preview, the system SHALL read the site status and the FC jobs in progress for the site. The system SHALL refuse the migrate, with exit code 2 and no write, when the site status is not Active, Inactive or Broken. The system SHALL also refuse it when FC has a job in Pending or Running state for the site. The error SHALL name the status or the job.

#### Scenario: Site status does not allow a migrate
- **WHEN** the site status on FC is `Suspended`
- **THEN** the system says that FC does not migrate a site in the `Suspended` status, sends no write request, and exits with code 2

#### Scenario: Job in progress
- **WHEN** FC has a `Backup Site` job in the Running state for the site
- **THEN** the system names the running job, sends no write request, and exits with code 2

### Requirement: Migrate preview
Before the confirmation, the system SHALL show a preview with: the profile, the team label and team name, the team owner email, the bench title and bench name, the site name, the site status, and the failing-patch mode. When `--skip-failing-patches` is set, the preview SHALL warn that FC continues past a failing patch. The preview SHALL be the last output before the confirmation prompt.

#### Scenario: Preview content
- **WHEN** the user reaches the confirmation for site `erp.acme.example.com`
- **THEN** the preview shows the profile, the team with its owner, the bench, the site with its status, and "Stop on a failing patch"

#### Scenario: Skip failing patches
- **WHEN** the user runs `fcm site-migrate erp.acme.example.com --skip-failing-patches`
- **THEN** the preview shows "Skip failing patches" with a warning that FC continues past a failing patch

### Requirement: Migrate confirmation
In interactive mode, the system SHALL send the migrate only after the user types the site name exactly. Any other input SHALL cancel the migrate with exit code 2 and no write. In non-interactive mode, the system SHALL send the migrate only when `--confirm` equals the site name. The system SHALL NOT provide a `--yes` option.

#### Scenario: Correct name typed
- **WHEN** the user types `erp.acme.example.com` at the confirmation for that site
- **THEN** the system sends the migrate request

#### Scenario: Wrong text typed
- **WHEN** the user types anything else, or presses Enter on an empty line
- **THEN** the system prints that the migrate was cancelled, sends no write request, and exits with code 2

#### Scenario: Script without confirm
- **WHEN** a script runs `fcm site-migrate erp.acme.example.com --json` with no `--confirm`
- **THEN** the system exits with code 2, sends no write request, and the error says that `--confirm erp.acme.example.com` is required

### Requirement: Migrate dry run
With `--dry-run`, the system SHALL run the checks and show the preview, and then exit with code 0. It SHALL send no write request and SHALL NOT ask for a confirmation.

#### Scenario: Dry run
- **WHEN** the user runs `fcm site-migrate erp.acme.example.com --dry-run`
- **THEN** the system shows the preview, says that nothing was sent, sends no write request, and exits with code 0

### Requirement: Migrate request
The system SHALL send the migrate as one POST to `press.api.site.migrate` with the team header, the site name, and the failing-patch mode. The system SHALL NOT retry it. When FC does not confirm the request, the system SHALL say that the migrate state on FC is not known, name `fcm site-show <site>`, and exit with code 6.

#### Scenario: Request body
- **WHEN** the user confirms the migrate of `erp.acme.example.com` in team `acme` with no option
- **THEN** the request is a POST to `press.api.site.migrate` with `X-Press-Team: acme` and a JSON body with `name` `erp.acme.example.com` and `skip_failing_patches` false

#### Scenario: Request times out
- **WHEN** the migrate request times out
- **THEN** the system sends no second request, says that the migrate state on FC is not known, names `fcm site-show erp.acme.example.com`, and exits with code 6

### Requirement: Migrate job watch
After FC accepts the request, the system SHALL find the new FC "Migrate Site" job of the site and show its steps as they change, until the job ends. The watch SHALL show the same liveness line as the deploy watch. With `--no-wait`, the system SHALL exit with code 0 after FC accepts the request. Ctrl+C SHALL stop the watch only: the system SHALL say that the migrate continues on FC and exit with code 130.

#### Scenario: Steps shown
- **WHEN** the migrate job runs the step "Migrate Site"
- **THEN** the watch shows that step as running, with its running time, and the time since the last FC answer

#### Scenario: No wait
- **WHEN** the user runs the migrate with `--no-wait` and FC accepts it
- **THEN** the system says that the migrate started, names `fcm site-show <site>`, and exits with code 0

#### Scenario: Watch stopped
- **WHEN** the user presses Ctrl+C during the watch
- **THEN** the system says that the migrate continues on FC, sends no request to stop it, and exits with code 130

### Requirement: Migrate result
When the job ends in Success, the system SHALL say that the site is migrated and exit with code 0. When the job ends in Failure, the system SHALL name the failed step and exit with code 8. When the system cannot find the new job within 2 minutes after FC accepts the request, it SHALL say that the result is not known, name `fcm site-show <site>`, and exit with code 6.

#### Scenario: Success
- **WHEN** the migrate job ends in Success
- **THEN** the system says that the site is migrated and exits with code 0

#### Scenario: Failure
- **WHEN** the migrate job ends in Failure at the step "Migrate Site"
- **THEN** the system names the step "Migrate Site" as failed and exits with code 8

#### Scenario: Job not found
- **WHEN** no new migrate job appears for the site within 2 minutes after FC accepts the request
- **THEN** the system says that the result is not known, names `fcm site-show <site>`, and exits with code 6
