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
The system SHALL send the update as one POST to `press.api.site.update` with the team header, the site name, the failing-patch mode, and `skip_backups` false. The system SHALL NOT provide an option that skips the FC backup. The system SHALL NOT retry the request. When FC does not confirm the request, the system SHALL say that the update state on FC is not known, name `fcm site-show <site>`, and exit with code 6.



#### Scenario: Request body
- **WHEN** the user confirms the update of `erp.acme.example.com` in team `acme` with no option
- **THEN** the request is a POST to `press.api.site.update` with `X-Press-Team: acme` and a JSON body with `name` `erp.acme.example.com`, `skip_failing_patches` false, and `skip_backups` false

#### Scenario: Request times out
- **WHEN** the update request times out
- **THEN** the system sends no second request, says that the update state on FC is not known, names `fcm site-show erp.acme.example.com`, and exits with code 6

### Requirement: Update record name
When FC confirms the request with the name of the new update record, the system SHALL show that name. When the answer holds no record name, the system SHALL continue with the watch.

#### Scenario: No record name in the answer
- **WHEN** FC accepts the update request and its answer holds no update record name
- **THEN** the system says that FC accepted the update, and starts the watch

### Requirement: Update watch
After FC accepts the request, the system SHALL follow the update with the site job watch. The expected job types SHALL be "Update Site Migrate" and "Update Site Pull". The system SHALL also follow the other jobs that show up on the site during the update, for example a backup or a recover job. The watch SHALL show the same liveness line as the deploy watch.



#### Scenario: Steps shown
- **WHEN** the "Update Site Migrate" job runs the step "Move Site"
- **THEN** the watch shows that step as running, with its running time, and the time since the last FC answer

#### Scenario: Recovery shown
- **WHEN** the update job fails and a "Recover Failed Site Update" job shows up on the site
- **THEN** the watch shows that FC restores the site, and keeps watching until the recover job ends

### Requirement: Update watch stop
With `--no-wait`, the system SHALL exit with code 0 after FC accepts the request. Ctrl+C SHALL stop the watch only: the system SHALL say that the update continues on FC and exit with code 130.

#### Scenario: No wait
- **WHEN** the user runs the update with `--no-wait` and FC accepts it
- **THEN** the system says that the update started, names `fcm site-show <site>`, and exits with code 0

#### Scenario: Watch stopped
- **WHEN** the user presses Ctrl+C during the watch
- **THEN** the system says that the update continues on FC, sends no request to stop it, and exits with code 130

### Requirement: Update result
When the update job ends in Success, the system SHALL say that the site is updated and exit with code 0. The system SHALL NOT name the new bench, because the site jobs and the site read do not give it. After the update ends, the system SHALL read the site status once and show it.



#### Scenario: Success
- **WHEN** the "Update Site Migrate" job ends in Success
- **THEN** the system says that the site is updated and exits with code 0

### Requirement: Update failure and unknown result
When the update job ends in Failure, the system SHALL name the failed job and step, show the FC output of the step, and exit with code 8. When no update job shows up within 2 minutes after FC accepts the request, the system SHALL say that the result is not known and exit with code 6.

#### Scenario: Failure with no recovery
- **WHEN** the update job ends in Failure, no recover job shows up, and the site status stays "Updating" for 10 minutes
- **THEN** the system names the failed job and step, says that FC started no recovery, names `fcm site-show <site>`, and exits with code 8

#### Scenario: Update job not found
- **WHEN** no "Update Site Migrate" or "Update Site Pull" job shows up for the site within 2 minutes after FC accepts the request
- **THEN** the system says that the result is not known, names `fcm site-show <site>`, and exits with code 6

### Requirement: Update failure outcome
For a failed update, the system SHALL say what FC did with the site. The outcome is "restored" when a recover job ends in Success, or when the site status becomes Active or Inactive after the failure. The outcome is "not restored" when a recover job ends in Failure, or when the site status becomes Broken.



#### Scenario: Restored, recover job not seen
- **WHEN** the update job fails, no recover job is seen, and the site status becomes Active
- **THEN** the system says that FC restored the site to the old bench, and exits with code 8

#### Scenario: Cancelled
- **WHEN** the update is cancelled on FC before an update job starts, so no update job shows up within 2 minutes
- **THEN** the system says that the result is not known, names `fcm site-show <site>`, and exits with code 6

### Requirement: Update failure outcome text
For "restored", the system SHALL say that FC restored the site to the old bench. For "not restored", the system SHALL say that FC could not restore the site, show the site status, and tell the user to contact FC support.

#### Scenario: Recovered
- **WHEN** the update job fails at the step "Backup Site Tables" and the "Recover Failed Site Update" job ends in Success
- **THEN** the system names the step "Backup Site Tables" as failed, says that FC restored the site to the old bench, and exits with code 8

#### Scenario: Fatal
- **WHEN** the update job fails and the recover job ends in Failure
- **THEN** the system names the failed step, says that FC could not restore the site, shows the site status, tells the user to contact FC support, and exits with code 8
