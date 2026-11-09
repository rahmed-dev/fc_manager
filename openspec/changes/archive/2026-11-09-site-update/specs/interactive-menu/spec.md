# Spec Delta

## MODIFIED Requirements

### Requirement: Action menu
After the bench pick, the system SHALL show an action menu for that bench with these entries: show the bench (`bench-show`), deploy app updates (`bench-deploy`), migrate a site (`site-migrate`), update a site (`site-update`), pick another bench, and quit. Each entry SHALL name its direct command. An action SHALL run with the same behavior as its direct command for that bench: the same FC requests, the same preview, and the same typed confirmation for a write.

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

### Requirement: Return to the action menu
When an action ends, the system SHALL show the action menu of the same bench again. This SHALL also apply when the action ends with an error or a cancelled confirmation: the system SHALL show the error and then the action menu. When the user stops a deploy watch, a migrate watch or an update watch with Ctrl+C, the system SHALL say that the job continues on FC and show the action menu.

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

### Requirement: Site step for site actions
When the user picks a site action, the system SHALL ask for one site of the picked bench before the action runs. The site step SHALL list only the sites of that bench, with the name and the status of each site. A site action MAY narrow the list further: for "Update a site", the site step SHALL list only the sites of that bench that FC marks as having an update. When no site is left to list, the system SHALL say so and show the action menu again.

#### Scenario: Sites of the bench only
- **WHEN** the user picks "Migrate a site" for bench `bench-1234`
- **THEN** the site step lists the sites of `bench-1234` only

#### Scenario: Bench with no site
- **WHEN** the user picks "Migrate a site" for a bench with no site
- **THEN** the system says that the bench has no site and shows the action menu of the same bench

#### Scenario: Only sites with an update
- **WHEN** the user picks "Update a site" for bench `bench-1234`, which has site `erp.acme.example.com` with an update and site `hr.acme.example.com` with no update
- **THEN** the site step lists `erp.acme.example.com` only

#### Scenario: No site with an update
- **WHEN** the user picks "Update a site" for a bench where no site has an update
- **THEN** the system says that no site of the bench has an update and shows the action menu of the same bench
