# Spec Delta

## MODIFIED Requirements

### Requirement: Action menu
After the bench pick, the system SHALL show an action menu for that bench with these entries: show the bench (`bench-show`), deploy app updates (`bench-deploy`), migrate a site (`site-migrate`), pick another bench, and quit. Each entry SHALL name its direct command. An action SHALL run with the same behavior as its direct command for that bench: the same FC requests, the same preview, and the same typed confirmation for a write.

#### Scenario: Show from the menu
- **WHEN** the user picks "Show bench" for bench `bench-1234`
- **THEN** the system shows the same output as `fcm bench-show bench-1234`

#### Scenario: Deploy from the menu
- **WHEN** the user picks "Deploy app updates" for bench `bench-1234`
- **THEN** the system starts the `bench-deploy` walk at the app step for `bench-1234`, and sends no write request before the preview and the typed bench title

#### Scenario: Migrate from the menu
- **WHEN** the user picks "Migrate a site" for bench `bench-1234` and then site `erp.acme.example.com`
- **THEN** the system runs the same checks and shows the same preview as `fcm site-migrate erp.acme.example.com`, and sends no write request before the typed site name

### Requirement: Target path on every prompt
Every prompt in the menu walk SHALL show the target path that is known at that step: the profile, then the team label, then the bench title and name, then the site name after a site pick. A write action SHALL keep its own full preview.

#### Scenario: Path at the action menu
- **WHEN** the action menu opens for bench `ACME Prod` (`bench-1234`) in team `ACME` with profile `work`
- **THEN** the prompt shows `work > ACME > ACME Prod (bench-1234)`

#### Scenario: Path after a site pick
- **WHEN** the user picks site `erp.acme.example.com` for a site action on that bench
- **THEN** the next prompt shows `work > ACME > ACME Prod (bench-1234) > erp.acme.example.com`

### Requirement: Return to the action menu
When an action ends, the system SHALL show the action menu of the same bench again. This SHALL also apply when the action ends with an error or a cancelled confirmation: the system SHALL show the error and then the action menu. When the user stops a deploy watch or a migrate watch with Ctrl+C, the system SHALL say that the job continues on FC and show the action menu.

#### Scenario: After a show
- **WHEN** `bench-show` ends in the menu
- **THEN** the action menu of the same bench opens again

#### Scenario: Wrong title typed in the menu
- **WHEN** the user types a wrong bench title at the deploy confirmation in the menu
- **THEN** the system prints that the deploy was cancelled, sends no write request, and shows the action menu of the same bench

#### Scenario: After a site action
- **WHEN** a migrate started from the menu ends
- **THEN** the action menu of the same bench opens again, with no site in the path

### Requirement: Menu navigation
Esc SHALL go back one step: from the site step to the action menu, from the action menu to the bench step, from the bench step to the team step, and from the team step out of the menu with exit code 0. Inside an action, Esc SHALL keep the behavior of that action's own walk. Ctrl+C at a menu prompt SHALL end `fcm` with exit code 130 and send nothing to FC. "Quit" SHALL end `fcm` with exit code 0.

#### Scenario: Esc at the action menu
- **WHEN** the user presses Esc at the action menu of bench `bench-1234` in team `acme`
- **THEN** the system shows the bench step for team `acme`

#### Scenario: Esc at the team step
- **WHEN** the user presses Esc at the team step
- **THEN** `fcm` ends with exit code 0

#### Scenario: Esc at the app step of a deploy in the menu
- **WHEN** the user presses Esc at the app step of a deploy started from the action menu
- **THEN** the system shows the action menu of the same bench

#### Scenario: Esc at the site step
- **WHEN** the user presses Esc at the site step of "Migrate a site"
- **THEN** the system shows the action menu of the same bench and sends nothing to FC

## ADDED Requirements

### Requirement: Site step for site actions
When the user picks a site action, the system SHALL ask for one site of the picked bench before the action runs. The site step SHALL list only the sites of that bench, with the name and the status of each site. When the bench has no site, the system SHALL say so and show the action menu again.

#### Scenario: Sites of the bench only
- **WHEN** the user picks "Migrate a site" for bench `bench-1234`
- **THEN** the site step lists the sites of `bench-1234` only

#### Scenario: Bench with no site
- **WHEN** the user picks "Migrate a site" for a bench with no site
- **THEN** the system says that the bench has no site and shows the action menu of the same bench
