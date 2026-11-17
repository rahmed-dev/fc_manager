# Spec Delta

## MODIFIED Requirements

### Requirement: Site update reads
The read allowlist SHALL include `press.api.site.check_for_updates`, so that the update command can read the update info of one site. The document read method SHALL NOT allow the doctype `Site Update`, because the update watch reads the site jobs and not the update record.

#### Scenario: Update info of one site
- **WHEN** the update command reads the update info of site `erp.acme.example.com`
- **THEN** the request is a GET to `press.api.site.check_for_updates` with the name `erp.acme.example.com`

#### Scenario: Update record read
- **WHEN** code asks the client for `press.api.client.get` with the doctype `Site Update`
- **THEN** the client raises an error and sends no request
