# Spec Delta

## MODIFIED Requirements

### Requirement: Update request
The system SHALL send the update as one POST to `press.api.site.update` with the team header, the site name, the failing-patch mode, and `skip_backups` false. The system SHALL NOT provide an option that skips the FC backup. The system SHALL NOT retry the request. When FC does not confirm the request, the system SHALL say that the update state on FC is not known, name `fcm site-show <site>`, and exit with code 6. When FC confirms the request with the name of the new update record, the system SHALL show that name. When the answer holds no record name, the system SHALL continue with the watch.

#### Scenario: Request body
- **WHEN** the user confirms the update of `erp.acme.example.com` in team `acme` with no option
- **THEN** the request is a POST to `press.api.site.update` with `X-Press-Team: acme` and a JSON body with `name` `erp.acme.example.com`, `skip_failing_patches` false, and `skip_backups` false

#### Scenario: Request times out
- **WHEN** the update request times out
- **THEN** the system sends no second request, says that the update state on FC is not known, names `fcm site-show erp.acme.example.com`, and exits with code 6

#### Scenario: No record name in the answer
- **WHEN** FC accepts the update request and its answer holds no update record name
- **THEN** the system says that FC accepted the update, and starts the watch

### Requirement: Update watch
After FC accepts the request, the system SHALL follow the update with the site job watch. The expected job types SHALL be "Update Site Migrate" and "Update Site Pull". The system SHALL also follow the other jobs that show up on the site during the update, for example a backup or a recover job. The watch SHALL show the same liveness line as the deploy watch. With `--no-wait`, the system SHALL exit with code 0 after FC accepts the request. Ctrl+C SHALL stop the watch only: the system SHALL say that the update continues on FC and exit with code 130.

#### Scenario: Steps shown
- **WHEN** the "Update Site Migrate" job runs the step "Move Site"
- **THEN** the watch shows that step as running, with its running time, and the time since the last FC answer

#### Scenario: Recovery shown
- **WHEN** the update job fails and a "Recover Failed Site Update" job shows up on the site
- **THEN** the watch shows that FC restores the site, and keeps watching until the recover job ends

#### Scenario: No wait
- **WHEN** the user runs the update with `--no-wait` and FC accepts it
- **THEN** the system says that the update started, names `fcm site-show <site>`, and exits with code 0

#### Scenario: Watch stopped
- **WHEN** the user presses Ctrl+C during the watch
- **THEN** the system says that the update continues on FC, sends no request to stop it, and exits with code 130

### Requirement: Update result
When the update job ends in Success, the system SHALL say that the site is updated and exit with code 0. The system SHALL NOT name the new bench, because the site jobs and the site read do not give it. When the update job ends in Failure, the system SHALL name the failed job and step, show the FC output of the step, and exit with code 8. When no update job shows up within 2 minutes after FC accepts the request, the system SHALL say that the result is not known and exit with code 6. After the update ends, the system SHALL read the site status once and show it.

#### Scenario: Success
- **WHEN** the "Update Site Migrate" job ends in Success
- **THEN** the system says that the site is updated and exits with code 0

#### Scenario: Failure with no recovery
- **WHEN** the update job ends in Failure, no recover job shows up, and the site status stays "Updating" for 10 minutes
- **THEN** the system names the failed job and step, says that FC started no recovery, names `fcm site-show <site>`, and exits with code 8

#### Scenario: Update job not found
- **WHEN** no "Update Site Migrate" or "Update Site Pull" job shows up for the site within 2 minutes after FC accepts the request
- **THEN** the system says that the result is not known, names `fcm site-show <site>`, and exits with code 6

### Requirement: Update failure outcome
For a failed update, the system SHALL say what FC did with the site. The outcome is "restored" when a recover job ends in Success, or when the site status becomes Active or Inactive after the failure. The outcome is "not restored" when a recover job ends in Failure, or when the site status becomes Broken. For "restored", the system SHALL say that FC restored the site to the old bench. For "not restored", the system SHALL say that FC could not restore the site, show the site status, and tell the user to contact FC support.

#### Scenario: Recovered
- **WHEN** the update job fails at the step "Backup Site Tables" and the "Recover Failed Site Update" job ends in Success
- **THEN** the system names the step "Backup Site Tables" as failed, says that FC restored the site to the old bench, and exits with code 8

#### Scenario: Restored, recover job not seen
- **WHEN** the update job fails, no recover job is seen, and the site status becomes Active
- **THEN** the system says that FC restored the site to the old bench, and exits with code 8

#### Scenario: Fatal
- **WHEN** the update job fails and the recover job ends in Failure
- **THEN** the system names the failed step, says that FC could not restore the site, shows the site status, tells the user to contact FC support, and exits with code 8

#### Scenario: Cancelled
- **WHEN** the update is cancelled on FC before an update job starts, so no update job shows up within 2 minutes
- **THEN** the system says that the result is not known, names `fcm site-show <site>`, and exits with code 6
