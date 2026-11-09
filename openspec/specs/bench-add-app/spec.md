# bench-add-app Specification

## Purpose
Lets a user add apps to a Frappe Cloud bench group from `fcm`: one or more published marketplace apps found with a fast search, or one app from a GitHub repository. Each add has a clear target, a preview and a typed confirmation. The apps reach the benches at the next deploy.

## Requirements

### Requirement: Add-app command
The system SHALL provide `fcm bench-add-app [BENCH]`. BENCH SHALL be resolved as for `bench-show`. With no BENCH in interactive mode, the system SHALL ask for the team, then a bench of that team. With no BENCH in non-interactive mode, the system SHALL exit with code 2 and send nothing.

#### Scenario: No bench in a script
- **WHEN** a script runs `fcm bench-add-app --json` with no BENCH
- **THEN** the system exits with code 2 and sends no request to FC

### Requirement: Source choice
In interactive mode with no `--app` and no `--repo`, the system SHALL ask where the app comes from: "From the marketplace" or "From GitHub". With `--app`, the source is the marketplace. With `--repo`, the source is GitHub. The system SHALL refuse `--app` together with `--repo`, with exit code 2. In non-interactive mode with neither option, the system SHALL exit with code 2.

#### Scenario: Choice on a terminal
- **WHEN** the user runs `fcm bench-add-app bench-1234` in a terminal
- **THEN** the system asks "From the marketplace" or "From GitHub"

#### Scenario: Both options
- **WHEN** the user passes `--app crm` and `--repo https://github.com/acme/tools`
- **THEN** the system exits with code 2 and sends no request to FC

### Requirement: Marketplace app list
The system SHALL read the apps that FC offers for the bench group once per bench in a session: the published marketplace apps that the group does not have. An app with no release source for the Frappe version of the group SHALL NOT be offered.

#### Scenario: One read per bench
- **WHEN** the user searches twice for apps on bench `bench-1234` in one menu session
- **THEN** the system sends one `all_apps` request for `bench-1234`

### Requirement: Marketplace search
The marketplace step SHALL be a search prompt. As the user types, the system SHALL show at most 10 matching apps, ranked in this order: exact app name, app name prefix, word prefix in the name or title, text inside the name or title, and the letters of the query in order. The search SHALL run on an index built once from the app list, and SHALL send no request to FC.

#### Scenario: Ranked matches
- **WHEN** the user types `help` and FC offers `helpdesk`, `whitelabel_helper` and 30 other apps that contain `help`
- **THEN** the prompt shows at most 10 apps, with `helpdesk` first

#### Scenario: Letters in order
- **WHEN** the user types `hlpdsk`
- **THEN** the prompt shows `helpdesk`

### Requirement: Several marketplace apps
After each marketplace pick, the system SHALL show the apps picked so far and ask whether to add another app. When an app has more than one release source, the system SHALL ask for the source. With `--app` repeated, the system SHALL pick each app by its app name. An app that FC does not offer SHALL exit with code 2, name the app, and send no write.

#### Scenario: Two apps
- **WHEN** the user picks `crm`, answers yes to "Add another app?", picks `helpdesk`, and answers no
- **THEN** the preview lists `crm` and `helpdesk`

#### Scenario: App not offered
- **WHEN** the user runs `fcm bench-add-app bench-1234 --app crm` and FC does not offer `crm`
- **THEN** the system names `crm`, sends no write request, and exits with code 2

### Requirement: Marketplace source option
With `--source <app>=<source>`, the system SHALL use that source for that app. In non-interactive mode, when an app has more than one source and no `--source` names one, the system SHALL exit with code 2 and list the sources with their branches.

#### Scenario: Several sources in a script
- **WHEN** a script runs `fcm bench-add-app bench-1234 --app lms --json` and `lms` has 2 sources
- **THEN** the system exits with code 2, sends no write request, and the error lists both branches

### Requirement: Marketplace add request
The system SHALL send all picked marketplace apps as one POST to `press.api.bench.add_apps` with the team header, the bench group name, and a list of `{app, source}`. The system SHALL NOT retry it.

#### Scenario: Request body
- **WHEN** the user confirms `crm` (source `src-crm`) and `lms` (source `src-lms-1`) for bench `bench-1234` in team `acme`
- **THEN** the request is one POST to `press.api.bench.add_apps` with `X-Press-Team: acme` and the body `name` `bench-1234`, `apps` `[{"app": "crm", "source": "src-crm"}, {"app": "lms", "source": "src-lms-1"}]`

### Requirement: GitHub repository step
For "From GitHub", the system SHALL offer the repositories of the FC GitHub installations of the team, and a choice to paste a public repository URL. With `--repo <url>`, the system SHALL use that URL. A URL that is not `https://github.com/<owner>/<repo>` SHALL exit with code 2 and send no write.

#### Scenario: Installed repositories
- **WHEN** the team has a GitHub installation `acme` with repository `tools`
- **THEN** the repository step lists `acme/tools` and an entry to paste a public URL

#### Scenario: Wrong URL
- **WHEN** the user gives `--repo https://gitlab.com/acme/tools`
- **THEN** the system says that it needs a GitHub URL, sends no write request, and exits with code 2

### Requirement: GitHub branch and app check
The system SHALL read the branches of the repository and ask for one, with the default branch first. With `--branch`, the system SHALL use that branch. The system SHALL then read the app name, the title, and the Frappe version range of that branch from FC. When the bench group already has an app with that name, the system SHALL exit with code 2 and send no write.

#### Scenario: App read from the branch
- **WHEN** the user picks branch `main` of `acme/tools`
- **THEN** the system reads the app name and title from FC and shows them in the preview

#### Scenario: App already on the bench
- **WHEN** the branch holds app `crm` and the bench group has `crm`
- **THEN** the system says that the bench already has `crm`, sends no write request, and exits with code 2

### Requirement: GitHub add request
The system SHALL add one GitHub app per run, as one POST to `press.api.client.run_doc_method` with the doctype `Release Group`, the bench group name, the method `add_app`, and the app name, title, repository URL, branch, and installation id when known. The system SHALL NOT retry it.

#### Scenario: Request body
- **WHEN** the user confirms app `tools` from `https://github.com/acme/tools` branch `main` for bench `bench-1234`
- **THEN** the request is one POST to `press.api.client.run_doc_method` with `dt` `Release Group`, `dn` `bench-1234`, `method` `add_app`, and `args.app` with `name` `tools`, the URL and the branch

### Requirement: Add-app preview
Before the confirmation, the system SHALL show a preview with: the profile, the team label and owner, the bench title and name, the Frappe version of the group, and each app with its title, branch and repository. For a GitHub app, the preview SHALL also show the Frappe version range of the branch. The preview SHALL say that the apps reach the benches only at the next deploy.

#### Scenario: Preview content
- **WHEN** the user reaches the confirmation for `crm` and `lms` on bench `bench-1234`
- **THEN** the preview shows the profile, the team with its owner, the bench, the Frappe version, both apps with their branches, and says that a deploy is needed

### Requirement: Add-app confirmation
In interactive mode, the system SHALL send the add request only after the user types the bench title exactly. Any other input SHALL cancel with exit code 2 and no write. In non-interactive mode, the system SHALL send the add request only when `--confirm` equals the bench FC name, as for `bench-deploy`. The system SHALL NOT provide a `--yes` option.

#### Scenario: Wrong text typed
- **WHEN** the user types anything other than the bench title
- **THEN** the system prints that the add was cancelled, sends no write request, and exits with code 2

#### Scenario: Script without confirm
- **WHEN** a script runs `fcm bench-add-app bench-1234 --app crm --json` with no `--confirm`
- **THEN** the system exits with code 2, sends no write request, and the error says that `--confirm bench-1234` is required

### Requirement: Add-app dry run
With `--dry-run`, the system SHALL do every read and pick, show the preview, and exit with code 0. It SHALL send no write request and SHALL NOT ask for a confirmation.

#### Scenario: Dry run
- **WHEN** the user runs `fcm bench-add-app bench-1234 --app crm --dry-run`
- **THEN** the system shows the preview, says that nothing was sent, sends no write request, and exits with code 0

### Requirement: Add-app result
When FC accepts the add request, the system SHALL name the added apps, say that they reach the benches at the next deploy, name `fcm bench-deploy <bench>`, and exit with code 0. When FC does not confirm the request, the system SHALL say that the app state on FC is not known, name `fcm bench-show <bench>`, and exit with code 6.

#### Scenario: Apps added
- **WHEN** FC accepts the add of `crm` to bench `bench-1234`
- **THEN** the system says that `crm` is added, names `fcm bench-deploy bench-1234`, and exits with code 0

#### Scenario: Request times out
- **WHEN** the add request times out
- **THEN** the system sends no second request, names `fcm bench-show bench-1234`, and exits with code 6
