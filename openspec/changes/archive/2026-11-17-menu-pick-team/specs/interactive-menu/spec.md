# Spec Delta

## MODIFIED Requirements

### Requirement: Action menu
After the bench pick, the system SHALL show an action menu for that bench with these entries: show the bench (`bench-show`), deploy app updates (`bench-deploy`), add an app (`bench-add-app`), migrate a site (`site-migrate`), update a site (`site-update`), install an app (`site-install-app`), pick another bench, pick another team, and quit. Each action entry SHALL name its direct command. An action SHALL run with the same FC requests, preview and typed confirmation as its direct command.

#### Scenario: Show from the menu
- **WHEN** the user picks "Show bench" for bench `bench-1234`
- **THEN** the system shows the same output as `fcm bench-show bench-1234`

#### Scenario: Deploy from the menu
- **WHEN** the user picks "Deploy app updates" for bench `bench-1234`
- **THEN** the system starts the `bench-deploy` walk at the app step for `bench-1234`, and sends no write request before the preview and the typed bench title

#### Scenario: Migrate from the menu
- **WHEN** the user picks "Migrate a site" for bench `bench-1234` and then site `erp.acme.example.com`
- **THEN** the system runs the same checks and shows the same preview as `fcm site-migrate erp.acme.example.com`, and sends no write request before the typed site name

#### Scenario: Update from the menu
- **WHEN** the user picks "Update a site" for bench `bench-1234` and then site `erp.acme.example.com`
- **THEN** the system runs the same checks and shows the same preview as `fcm site-update erp.acme.example.com`, and sends no write request before the typed site name

#### Scenario: Add an app from the menu
- **WHEN** the user picks "Add an app" for bench `bench-1234`
- **THEN** the system shows the same source choice, app steps and preview as `fcm bench-add-app bench-1234`, and sends no write request before the typed bench title

#### Scenario: Install an app from the menu
- **WHEN** the user picks "Install an app" for bench `bench-1234` and then site `erp.acme.example.com`
- **THEN** the system runs the same checks, app step and preview as `fcm site-install-app erp.acme.example.com`, and sends no write request before the typed site name

## ADDED Requirements

### Requirement: Team change from the action menu
The system SHALL show the "Pick another team" entry only when the profile reaches more than one team. "Pick another team" SHALL open the team step of the menu walk. The system SHALL send no request to FC before the team step shows.

#### Scenario: Pick another team
- **WHEN** the profile reaches teams `acme` and `globex`, and the user picks "Pick another team" at the action menu of bench `bench-1234` in team `acme`
- **THEN** the system shows the team step with both teams, sends no request to FC before the team step shows, and after the user picks `globex`, lists the benches of team `globex` only

#### Scenario: One team, no team entry
- **WHEN** the profile reaches only team `acme`
- **THEN** the action menu shows no "Pick another team" entry, and shows "Pick another bench" and "Quit" as the last two entries
