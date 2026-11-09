# Proposal

## Why

One Frappe Cloud (FC) user is often a member of many teams, for example an own team and several client teams. The FC web dashboard shows one team at a time, so it is slow to find a bench or a site across teams. This change builds the safe, read-only base of `fc_manager`. Later changes (write actions, TUI) use the same base. The repository will be public on GitHub, so credential safety must be correct from the first change.

## What Changes

- New Python package and CLI (command name `fcm`, an assumption that is easy to change).
- **Profiles**: a profile is one FC login, which has one API key and one API secret. The tool supports more than one profile. The key and the secret go into the OS keyring only. Environment variables are a fallback for CI and for hosts with no keyring.
- **Team discovery**: the tool reads all teams that a profile can reach. It sends the `X-Press-Team` header on each request to select a team. The user never types a team list.
- **Inventory listing**: the CLI lists teams, benches (FC "release groups"), and sites, across one team or all teams. It also shows the details of one site, with its installed apps.
- **Output**: formatted tables on a terminal, a `--json` option for scripts, and clear error messages with a hint and a stable exit code.
- **Security**:
  - The tool redacts secrets from all output, logs, and error text.
  - The tool uses HTTPS only.
  - The HTTP client calls only an allowlist of read-only FC API methods.
- No write actions in this change. Deploy, app install, and the TUI are later changes.

## Capabilities

### New Capabilities

- `credential-profiles`: add, list, test, and remove profiles. Secret storage in the OS keyring, the environment-variable fallback, and the selection of the active profile.
- `fc-api-access`: how the tool talks to the FC API. This covers the auth headers, team selection, HTTPS-only, the read-only method allowlist, secret redaction, and the mapping of FC errors to tool errors.
- `cloud-inventory`: discovery and listing of teams, benches, and sites across teams. This covers filters and the site detail view with installed apps.
- `cli-output`: the output format (tables and JSON), error message format, exit codes, and debug output.

### Modified Capabilities

None. The project has no specs yet.

## Impact

- New code under `src/fc_manager/`, with tests under `tests/`.
- New runtime dependencies: an HTTP client, a CLI framework, a terminal table library, `keyring`, and a config-directory library. The design names the exact choices.
- External system: the FC API at `https://cloud.frappe.io/api/method/press.api.*` (FC moved it from `frappecloud.com`, which now answers with a redirect). This change uses read endpoints only.
- User machine: one config file in the user config directory (no secrets in it), and entries in the OS keyring.
