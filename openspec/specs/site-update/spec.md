# site-update Specification

## Purpose
Lets a user move one Frappe Cloud site to the newest bench of its bench group from `fcm`, as the FC dashboard "Update" does. The user gets a clear target, a preview of the app changes, a typed confirmation, and a live view of the FC update until it ends.

## Requirements

### Requirement: Update command
The system SHALL provide `fcm site-update [SITE]`. It SHALL send one FC update request for one site. SITE SHALL be the site FC name or a unique part of it, resolved as for `site-show`. With no SITE in interactive mode, the system SHALL ask for the team, then the bench, then a site of that bench that has an update. With no SITE in non-interactive mode, the system SHALL exit with code 2 and send nothing.

#### Scenario: Site given
- **WHEN** the user runs `fcm site-update erp.acme.example.com`
- **THEN** the system runs the checks for that site and then shows the preview

#### Scenario: No site on a terminal
- **WHEN** the user runs `fcm site-update` in a terminal
- **THEN** the system asks for the team, then a bench of that team, then a site of that bench that has an update

#### Scenario: No site in a script
- **WHEN** a script runs `fcm site-update --json` with no SITE
- **THEN** the system exits with code 2 and sends no request to FC

### Requirement: Update checks
Before the preview, the system SHALL read the FC update info, the status, and the FC jobs in progress for the site. When FC reports no update for the site, the system SHALL say so and exit with code 0, with no write. The system SHALL refuse the update, with exit code 2 and no write, when the site status is not Active or Inactive. The system SHALL also refuse it when FC has a job in Pending or Running state for the site. The error SHALL name the status or the job.

#### Scenario: No update
- **WHEN** FC reports no update for site `erp.acme.example.com`
- **THEN** the system says that the site has no update, sends no write request, and exits with code 0

#### Scenario: Site status does not allow an update
- **WHEN** the site has an update and its status on FC is `Broken`
- **THEN** the system says that `fcm` does not update a site in the `Broken` status, sends no write request, and exits with code 2

#### Scenario: Job in progress
- **WHEN** FC has a `Backup Site` job in the Running state for the site
- **THEN** the system names the running job, sends no write request, and exits with code 2

### Requirement: Update preview
Before the confirmation, the system SHALL show a preview with: the profile, the team label and team name, the team owner email, the bench title and bench name, the site name, the site status, each app with an update and its current and next version, and the failing-patch mode. An app version SHALL be the release tag, else the short commit hash. The preview SHALL be the last output before the confirmation prompt.

#### Scenario: Preview content
- **WHEN** the user reaches the confirmation for site `erp.acme.example.com`, and FC reports an update of `erpnext` from `v16.1.0` to `v16.2.0`
- **THEN** the preview shows the profile, the team with its owner, the bench, the site with its status, `erpnext  v16.1.0 -> v16.2.0`, "Site is down during the update; FC takes a backup first", and "Stop on a failing patch"

### Requirement: Update preview notes
The preview SHALL say that FC takes the site down during the update and takes a backup of the site first. The preview SHALL note an app whose branch changes. When `--skip-failing-patches` is set, the preview SHALL warn that FC continues past a failing patch.

#### Scenario: Branch change
- **WHEN** FC reports that the next release of `hrms` comes from branch `version-16` and the current one from `version-15`
- **THEN** the preview notes the branch change of `hrms` from `version-15` to `version-16`

#### Scenario: Skip failing patches
- **WHEN** the user runs `fcm site-update erp.acme.example.com --skip-failing-patches`
- **THEN** the preview shows "Skip failing patches" with a warning that FC continues past a failing patch

### Requirement: Update confirmation
In interactive mode, the system SHALL send the update only after the user types the site name exactly. Any other input SHALL cancel the update with exit code 2 and no write. In non-interactive mode, the system SHALL send the update only when `--confirm` equals the site name. The system SHALL NOT provide a `--yes` option.

#### Scenario: Correct name typed
- **WHEN** the user types `erp.acme.example.com` at the confirmation for that site
- **THEN** the system sends the update request

#### Scenario: Wrong text typed
- **WHEN** the user types anything else, or presses Enter on an empty line
- **THEN** the system prints that the update was cancelled, sends no write request, and exits with code 2

#### Scenario: Script without confirm
- **WHEN** a script runs `fcm site-update erp.acme.example.com --json` with no `--confirm`
- **THEN** the system exits with code 2, sends no write request, and the error says that `--confirm erp.acme.example.com` is required

### Requirement: Update dry run
With `--dry-run`, the system SHALL run the checks and show the preview, and then exit with code 0. It SHALL send no write request and SHALL NOT ask for a confirmation.

#### Scenario: Dry run
- **WHEN** the user runs `fcm site-update erp.acme.example.com --dry-run`
- **THEN** the system shows the preview, says that nothing was sent, sends no write request, and exits with code 0

### Requirement: Update request
The system SHALL send the update as one POST to `press.api.site.update` with the team header, the site name, the failing-patch mode, and `skip_backups` false. The system SHALL NOT provide an option that skips the FC backup. The system SHALL NOT retry the request. When FC does not confirm the request, or confirms it without the name of the new update record, the system SHALL say that the update state on FC is not known, name `fcm site-show <site>`, and exit with code 6.

#### Scenario: Request body
- **WHEN** the user confirms the update of `erp.acme.example.com` in team `acme` with no option
- **THEN** the request is a POST to `press.api.site.update` with `X-Press-Team: acme` and a JSON body with `name` `erp.acme.example.com`, `skip_failing_patches` false, and `skip_backups` false

#### Scenario: Request times out
- **WHEN** the update request times out
- **THEN** the system sends no second request, says that the update state on FC is not known, names `fcm site-show erp.acme.example.com`, and exits with code 6

#### Scenario: No record name in the answer
- **WHEN** FC accepts the update request and its answer holds no update record name
- **THEN** the system says that the update state on FC is not known, names `fcm site-show erp.acme.example.com`, and exits with code 6

### Requirement: Update watch
After FC accepts the request, the system SHALL read the new FC update record by its name and show its status and its steps as they change, until the update ends. The watch SHALL show the same liveness line as the deploy watch. With `--no-wait`, the system SHALL exit with code 0 after FC accepts the request. Ctrl+C SHALL stop the watch only: the system SHALL say that the update continues on FC and exit with code 130.

#### Scenario: Steps shown
- **WHEN** the update runs the step "Move Site"
- **THEN** the watch shows that step as running, with its running time, and the time since the last FC answer

#### Scenario: Recovery shown
- **WHEN** the update fails and FC starts to restore the site
- **THEN** the watch shows that FC restores the site, and keeps watching until the restore ends

#### Scenario: No wait
- **WHEN** the user runs the update with `--no-wait` and FC accepts it
- **THEN** the system says that the update started, names `fcm site-show <site>`, and exits with code 0

#### Scenario: Watch stopped
- **WHEN** the user presses Ctrl+C during the watch
- **THEN** the system says that the update continues on FC, sends no request to stop it, and exits with code 130

### Requirement: Update result
When the update ends in Success, the system SHALL say that the site is updated, name the new bench, and exit with code 0. When the update ends in Recovered or Fatal, or stays in Failure for 10 minutes with no FC recovery, the system SHALL name the failed step and exit with code 8. A Cancelled update SHALL also exit with code 8. After the update ends, the system SHALL read the site status once and show it.

#### Scenario: Success
- **WHEN** the update ends in Success
- **THEN** the system says that the site is updated, names the new bench, and exits with code 0

#### Scenario: Failure with no recovery
- **WHEN** the update stays in Failure for 10 minutes and FC starts no recovery
- **THEN** the system names the failed step, names `fcm site-show <site>`, and exits with code 8

### Requirement: Update failure outcome
For a failed update, the system SHALL say what FC did with the site. For Recovered, the system SHALL say that FC restored the site to the old bench. For Fatal, the system SHALL say that FC could not restore the site, show the site status, and tell the user to contact FC support. For Cancelled, the system SHALL say that the update was cancelled on FC.

#### Scenario: Recovered
- **WHEN** the update fails at the step "Migrate Site" and FC restores the site to the old bench
- **THEN** the system names the step "Migrate Site" as failed, says that FC restored the site to the old bench, and exits with code 8

#### Scenario: Fatal
- **WHEN** the update ends in Fatal
- **THEN** the system names the failed step, says that FC could not restore the site, shows the site status, tells the user to contact FC support, and exits with code 8

#### Scenario: Cancelled
- **WHEN** the update record ends in Cancelled
- **THEN** the system says that the update was cancelled on FC and exits with code 8
