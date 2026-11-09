# Spec Delta

## MODIFIED Requirements

### Requirement: Site step for site actions
When the user picks a site action, the system SHALL ask for one site of the picked bench before the action runs. The site step SHALL list only the sites of that bench, with the name and the status of each site. A site action MAY narrow the list further: for "Update a site", the site step SHALL list only the sites of that bench that FC marks as having an update. When no site is left to list, the system SHALL say so and show the action menu again. When exactly one site is left to list, the system SHALL pick that site without a prompt and SHALL print the name of the picked site. In the site step, Enter and Space SHALL both pick the site under the pointer. The same site step SHALL serve the walk of `site-migrate` and `site-update` with no SITE.

#### Scenario: Sites of the bench only
- **WHEN** the user picks "Migrate a site" for bench `bench-1234`
- **THEN** the site step lists the sites of `bench-1234` only

#### Scenario: Bench with no site
- **WHEN** the user picks "Migrate a site" for a bench with no site
- **THEN** the system says that the bench has no site and shows the action menu of the same bench

#### Scenario: Only sites with an update
- **WHEN** the user picks "Update a site" for bench `bench-1234`, which has sites `erp.acme.example.com` and `crm.acme.example.com` with an update and site `hr.acme.example.com` with no update
- **THEN** the site step lists `erp.acme.example.com` and `crm.acme.example.com` only

#### Scenario: No site with an update
- **WHEN** the user picks "Update a site" for a bench where no site has an update
- **THEN** the system says that no site of the bench has an update and shows the action menu of the same bench

#### Scenario: Only one site left
- **WHEN** the user picks "Update a site" for bench `bench-1234`, and only site `erp.acme.example.com` has an update
- **THEN** the system shows no site list, prints that it picked `erp.acme.example.com`, and continues to the checks and the preview of that site

#### Scenario: Space picks a site
- **WHEN** the site step lists 2 sites and the user presses Space on `crm.acme.example.com`
- **THEN** the system picks `crm.acme.example.com`, as Enter does
