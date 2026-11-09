# Spec Delta

## MODIFIED Requirements

### Requirement: App update selection
The system SHALL show each app with an available update: app name, current version and next version (the release tag; else the version in a FC release message such as "Bumped to Version 16.55.2"; else the short commit hash), and a note when the branch changes. No app SHALL be selected by default. The user SHALL select each app to deploy. The system SHALL deploy the next release that FC offers for each selected app, and SHALL NOT offer a yanked release.

#### Scenario: Default selection
- **WHEN** FC reports updates for `erpnext` and `hrms`
- **THEN** neither app is selected when the app step opens

#### Scenario: One app selected
- **WHEN** FC reports updates for `erpnext` and `hrms`, and the user selects `hrms` only
- **THEN** the deploy plan holds `hrms` only

#### Scenario: No app selected
- **WHEN** the user confirms the app step with no app selected and FC reports no removed app
- **THEN** the system does not continue to the confirmation, tells the user to select at least one app, and shows the app step again
