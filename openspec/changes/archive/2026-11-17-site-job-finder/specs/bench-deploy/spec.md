# Spec Delta

## MODIFIED Requirements

### Requirement: Site update wait
After the new bench is ready, the system SHALL follow the site update job ("Update Site Migrate" or "Update Site Pull") of each selected site with the site job watch, for all selected sites in the same watch. It SHALL show each site with its state. The find limit for a site update job SHALL be 30 minutes. A failed site update SHALL get the same outcome check as `fcm site-update`.

#### Scenario: Site moves after the bench is ready
- **WHEN** the new bench is ready, and the "Update Site Migrate" job of selected site `erp.acme.com` ends in Success
- **THEN** the system reports `erp.acme.com` as updated

#### Scenario: Site update job is not there yet
- **WHEN** the new bench is ready, and no site update job of selected site `erp.acme.com` shows up for some polls
- **THEN** the system shows `erp.acme.com (waiting)` and keeps polling

#### Scenario: Site update fails
- **WHEN** the "Update Site Migrate" job of selected site `erp.acme.com` ends in Failure at the step "Backup Site Tables" with the output `mariadb-dump: Got error: 1040: "Too many connections" when trying to connect`
- **THEN** the system names the site, the job "Update Site Migrate" and the step "Backup Site Tables", shows that output, and says what FC did with the site

#### Scenario: Site move not confirmed in time
- **WHEN** no site update job of selected site `erp.acme.com` shows up within 30 minutes after the new bench is ready
- **THEN** the system says that FC did not start the update of `erp.acme.com`, says that its result is not known, names `fcm site-show erp.acme.com`, and exits with code 6

### Requirement: Deploy result
On success, the system SHALL print the bench, the deployed apps, and the updated sites, and exit with code 0. When FC rejects the deploy request, the system SHALL show the FC message and exit with the code of the error kind, and SHALL NOT retry. When the deploy fails on FC after FC accepted it, the system SHALL show the failed step and the FC message, and exit with code 8. When the bench deploy succeeds, the system SHALL print one result for each selected site. When the update of one or more selected sites fails, the system SHALL exit with code 8. When no site update fails and the result of one or more sites is not known, the system SHALL exit with code 6.

#### Scenario: Build fails
- **WHEN** the FC build fails at step `Install apps`
- **THEN** the system names the step, shows the FC message, and exits with code 8

#### Scenario: FC validation refuses the deploy
- **WHEN** FC answers the deploy request with a validation error, for example from its "will fail" check
- **THEN** the system shows the FC message, sends no second request, and exits with code 1

#### Scenario: One of two site updates fails
- **WHEN** the bench deploy succeeds, the update of site `a.acme.com` succeeds, and the update of site `b.acme.com` fails
- **THEN** the system reports `a.acme.com` as updated, reports `b.acme.com` as failed with its job, its step and the FC output, and exits with code 8

#### Scenario: Site result not known
- **WHEN** the bench deploy succeeds, the update of site `a.acme.com` succeeds, and no site update job of site `b.acme.com` shows up within 30 minutes
- **THEN** the system reports `a.acme.com` as updated, says that the result of `b.acme.com` is not known, and exits with code 6

#### Scenario: Deploy with no selected site
- **WHEN** the bench deploy succeeds and the user selected no site
- **THEN** the system prints the bench and the deployed apps, follows no site job, and exits with code 0
