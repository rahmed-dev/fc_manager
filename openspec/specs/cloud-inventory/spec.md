# cloud-inventory Specification

## Purpose

Lets a user see the teams, benches (FC release groups), and sites that one FC login can reach, across all of its teams, from one place.

## Requirements

### Requirement: Discover teams
The system SHALL find every enabled team that the active profile can reach, from FC, without user input.

#### Scenario: Member of several teams
- **WHEN** the profile user is a member of teams `riz-own`, `client-acme`, and `client-beta`
- **THEN** `fcm team-list` lists all 3 teams with the team name, the team title, and the owner email

### Requirement: Team label
Wherever output names a team, the system SHALL show the team title when no other discovered team has the same title. When 2 or more teams share a title, the system SHALL show the team owner email for each of them, or the team name when the owner email is missing.

#### Scenario: Unique titles
- **WHEN** the teams have the titles `Own Team`, `ACME Corp`, and `Beta Ltd`
- **THEN** list rows show those titles in the Team column

#### Scenario: Shared default title
- **WHEN** 13 teams all have the title `Parent Team` and different owner emails
- **THEN** list rows, pickers, and errors show the owner email of each team, not `Parent Team`

### Requirement: Team scope for list commands
Each list command SHALL accept `--team <name>` to limit the result to one team. With no `--team`, the command SHALL cover all discovered teams. A `--team` value that is not a discovered team SHALL be an error.

#### Scenario: All teams
- **WHEN** the user runs `fcm bench-list` with no `--team`
- **THEN** the system lists benches from every discovered team, and each row shows its team

#### Scenario: Unknown team
- **WHEN** the user passes `--team nope` and `nope` is not the name or title of a discovered team
- **THEN** the system stops with an error that lists the valid team names and titles

### Requirement: Resolve a team, bench, or site by name or title
Wherever the user gives a team, a bench, or a site, the system SHALL accept the FC name or the title; a team SHALL also match its owner email. The system SHALL first try an exact match on the name, then (teams only) a case-insensitive match on the owner email, then an exact, case-insensitive match on the title. One match SHALL resolve. More than one match SHALL be ambiguous.

#### Scenario: Team by title
- **WHEN** the user passes `--team "ACME Corp"` and one team has the title `ACME Corp`
- **THEN** the system uses that team's FC name in requests

#### Scenario: Team by owner email
- **WHEN** the user passes `--team client@acme.example.com` and one team has that owner email
- **THEN** the system uses that team

#### Scenario: Bench by name
- **WHEN** the user passes `--bench bench-1234`
- **THEN** the system uses bench `bench-1234`, with no title lookup

#### Scenario: Two benches share a title
- **WHEN** the user passes `--bench "Prod"` and benches in 2 teams have the title `Prod`
- **THEN** the target is ambiguous, and the cli-output picker rules apply

#### Scenario: No match
- **WHEN** no item matches by name or by title
- **THEN** the system reports a not-found error and lists up to 5 close matches

### Requirement: Partial failure across teams
When a list command covers several teams and one team fails, the system SHALL still show the results from the other teams. The system SHALL report each failed team with its error, and SHALL exit with a non-zero code.

#### Scenario: One team denies access
- **WHEN** `fcm site-list` runs over 3 teams and FC returns a permission error for one team
- **THEN** the system shows sites from the 2 other teams, names the failed team with the error, and exits non-zero

### Requirement: List benches
The system SHALL list benches (release groups) with team, name, title, Frappe version, status, number of sites, and number of apps.

#### Scenario: Benches in one team
- **WHEN** the user runs `fcm bench-list --team acme`
- **THEN** each row shows team, name, title, version, status, site count, and app count

### Requirement: List sites
The system SHALL list sites with team, site name, bench (release group), status, Frappe version, region, and an update-available marker.

#### Scenario: Sites in one team
- **WHEN** the user runs `fcm site-list --team acme`
- **THEN** each row shows team, site name, bench, status, version, region, and the update marker

### Requirement: Filter sites by bench
The system SHALL accept `--bench <name>` on `fcm site-list` and show only the sites on that bench.

#### Scenario: Bench filter
- **WHEN** the user runs `fcm site-list --bench acme-prod-v15`
- **THEN** only sites whose bench is `acme-prod-v15` appear

### Requirement: Filter sites by status
The system SHALL accept `--status` on `fcm site-list` with the values `active`, `inactive`, `broken`, `trial`, and `update-available`.

#### Scenario: Update available
- **WHEN** the user runs `fcm site-list --status update-available`
- **THEN** only sites with an available bench update appear

### Requirement: Site detail with installed apps
The system SHALL show the details of one site: team, bench, status, Frappe version, region, server, and the installed apps. Each app row SHALL show app name, title, branch, repository, and commit hash.

#### Scenario: Site found
- **WHEN** the user runs `fcm site-show erp.acme.com`
- **THEN** the system shows the site details and the installed apps table

#### Scenario: Team not given
- **WHEN** the user runs `fcm site-show erp.acme.com` with no `--team`
- **THEN** the system finds the team that owns the site across the discovered teams

#### Scenario: Site not found
- **WHEN** no discovered team has a site with that name
- **THEN** the system reports a not-found error and exits with the not-found exit code

### Requirement: Partial site detail when FC denies it
When FC lists a site but denies its detail or its installed apps to the user's role, the system SHALL still show the fields it has from the site list (team, bench, status, version, region, update marker). It SHALL state that details and apps are not permitted for the user's role in that team, and SHALL exit with the permission exit code.

#### Scenario: Role allows listing only
- **WHEN** the user runs `fcm site-show erp.acme.com` and FC returns a permission error for the site detail
- **THEN** the system shows the site's team, bench, status, version, region, and update marker, says that details and apps are not permitted for the user's role in that team, and exits with code 4

### Requirement: No write calls
The inventory commands SHALL NOT change any state on FC.

#### Scenario: Any inventory command
- **WHEN** the user runs any `team list`, `bench list`, `site list`, or `site show` command
- **THEN** the system calls read-only FC methods only
