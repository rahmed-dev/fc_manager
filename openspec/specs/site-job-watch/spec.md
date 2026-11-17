# site-job-watch Specification

## Purpose
Defines how fcm finds and follows the FC jobs of one site after an action (deploy, update, migrate, install), and how it reports the result of those jobs, so that every action reports a failure the same way: the job, the failed step and the FC error text.

## Requirements

### Requirement: Job discovery
After an action on a site, the system SHALL find the FC jobs of that site through the running jobs of the site. Each action SHALL name the job types that it expects. The system SHALL poll FC no more often than every 2 seconds.

#### Scenario: Expected job shows up
- **WHEN** FC accepts a migrate of site `erp.acme.example.com`, and a "Migrate Site" job shows up in the running jobs of the site
- **THEN** the system follows that job

#### Scenario: Other job types on the site
- **WHEN** a "Backup Site" job and an "Update Site Migrate" job show up on the site during an update
- **THEN** the system follows both jobs and shows each job with its type and its state

### Requirement: Job follow-up
The system SHALL follow each job that it finds until the job ends in Success or Failure. It SHALL show the steps of the job and the state of each step as they change.

#### Scenario: Steps shown
- **WHEN** the followed job runs the step "Backup Site Tables"
- **THEN** the watch shows that step as running, with its running time

### Requirement: Failed job report
When a followed job ends in Failure, the system SHALL name the job type and the failed step, and SHALL show the FC output of the failed step. The output SHALL pass through secret redaction, and the system SHALL show at most its last 500 characters.

#### Scenario: Backup step fails
- **WHEN** the job "Update Site Migrate" ends in Failure at the step "Backup Site Tables" with the output `mariadb-dump: Got error: 1040: "Too many connections" when trying to connect`
- **THEN** the system names "Update Site Migrate" and "Backup Site Tables" as failed, and shows that output

### Requirement: Job not found
When no job of an expected type shows up for the site within the find limit of the action, the system SHALL say that the result is not known, name the site and `fcm site-show <site>`, show the site status, and exit with code 6. The find limit SHALL be 2 minutes, unless the action names another limit.

#### Scenario: No job in 2 minutes
- **WHEN** FC accepts a migrate, and no "Migrate Site" job shows up for the site within 2 minutes
- **THEN** the system says that the result is not known, names `fcm site-show <site>`, and exits with code 6

### Requirement: Short job limit
The system SHALL see a job only while the job is Pending or Running. The documentation of the watch SHALL say that a job that starts and ends between two polls is not seen.

#### Scenario: Job ends between two polls
- **WHEN** an expected job starts and ends between two polls, and no other expected job shows up within the find limit
- **THEN** the system says that the result is not known and exits with code 6

### Requirement: Job watch liveness
On a terminal, the site job watch SHALL show the same liveness line as the deploy watch: the time since the last FC answer, the poll count, the elapsed time, and how long the current step has run. The JSON and plain-text outputs SHALL print a line only when the FC data changes.

#### Scenario: Long step on a terminal
- **WHEN** a followed job runs one step for 5 minutes with no change in FC data
- **THEN** the status line shows "last FC answer N s ago" with N reset at each FC answer, and the poll count goes up
