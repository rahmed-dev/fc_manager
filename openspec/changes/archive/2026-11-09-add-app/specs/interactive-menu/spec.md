# Spec Delta

## MODIFIED Requirements

### Requirement: Action menu
After the bench pick, the system SHALL show an action menu for that bench with these entries: show the bench (`bench-show`), deploy app updates (`bench-deploy`), add an app (`bench-add-app`), migrate a site (`site-migrate`), update a site (`site-update`), install an app (`site-install-app`), pick another bench, and quit. Each entry SHALL name its direct command. An action SHALL run with the same FC requests, preview and typed confirmation as its direct command for that bench.

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

### Requirement: Return to the action menu
When an action ends, the system SHALL show the action menu of the same bench again. This SHALL also apply when the action ends with an error or a cancelled confirmation: the system SHALL show the error and then the action menu. When the user stops a deploy, migrate, update or install watch with Ctrl+C, the system SHALL say that the job continues on FC and show the action menu.

#### Scenario: After a show
- **WHEN** `bench-show` ends in the menu
- **THEN** the action menu of the same bench opens again

#### Scenario: Wrong title typed in the menu
- **WHEN** the user types a wrong bench title at the deploy confirmation in the menu
- **THEN** the system prints that the deploy was cancelled, sends no write request, and shows the action menu of the same bench

#### Scenario: After a site action
- **WHEN** a migrate started from the menu ends
- **THEN** the action menu of the same bench opens again, with no site in the path

#### Scenario: Update watch stopped in the menu
- **WHEN** the user presses Ctrl+C during an update watch started from the menu
- **THEN** the system says that the update continues on FC and shows the action menu of the same bench

#### Scenario: Install watch stopped in the menu
- **WHEN** the user presses Ctrl+C during an install watch started from the menu
- **THEN** the system says that the install continues on FC and shows the action menu of the same bench

## ADDED Requirements

### Requirement: Deploy after an add
When FC accepts an add request that the user started from the menu, the system SHALL ask "Deploy now?" with No as the default. A yes SHALL start the "Deploy app updates" action of the same bench, with its own app step, preview and typed bench title. A no or Esc SHALL show the action menu of the same bench. The question SHALL send nothing to FC.

#### Scenario: Deploy after the add
- **WHEN** the user adds app `crm` to bench `bench-1234` from the menu and answers yes to "Deploy now?"
- **THEN** the system starts the `bench-deploy` walk at the app step for `bench-1234`, and sends no deploy request before the preview and the typed bench title

#### Scenario: No deploy after the add
- **WHEN** the user answers no to "Deploy now?"
- **THEN** the system sends no request and shows the action menu of the same bench
