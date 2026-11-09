# Tasks

## 1. Project setup

- [x] 1.1 Create `pyproject.toml` (uv, `src/` layout, Python >= 3.11, console script `fcm`) with the dependencies from design D2. Verify that `uv sync` succeeds and `uv run fcm --help` prints the help text.
- [x] 1.2 Add the `ruff` and `pytest` config, plus an empty `tests/` package. Verify that `uv run ruff check .` and `uv run pytest` both pass.
- [x] 1.3 Add a GitHub Actions workflow that runs ruff and pytest on Linux and macOS for Python 3.11 and 3.13. Verify that the workflow file passes `actionlint`, or a manual YAML check if `actionlint` is not installed.

## 2. API client and FC contract check

- [x] 2.1 Spike with a real FC key (the user runs it, or supplies a test key through `FCM_API_KEY` / `FCM_API_SECRET`). Confirm that `X-Press-Team` selects the team for `bench.all` and `site.all`. Record one real response for each allowlisted method and one real error body for each of auth, permission, and not-found. Save them under `tests/fixtures/fc/`, with emails, IPs, and hostnames anonymized. Verify that the fixtures exist and contain no secret or personal data. If the header does not select the team, stop and raise the `switch_team` fallback with the user (design Risks).
- [x] 2.2 Implement `redact.py` (secret registry, `Authorization` scrubbing) and the masked credential class. Verify with unit tests that the redaction helper replaces registered secrets and header values, and that `repr()` and `str()` of the credential class show `***`.
- [x] 2.3 Implement the tool error types with their kinds and exit codes (design D6). Verify with a unit test that each kind maps to the exit code in the cli-output spec.
- [x] 2.4 Implement `FCClient`: base URL with an HTTPS-only check, auth header, `X-Press-Team`, GET with JSON-encoded complex params, timeouts, and the frozen allowlist (D4). Verify with `respx` tests that the client sends both headers, refuses a non-allowlisted method with no request, and rejects an `http://` base URL.
- [x] 2.5 Implement error mapping and bounded retries (D6), with the parse of `_server_messages`, `message`, and `exception`, plus the non-JSON fallback. Verify with `respx` tests, using the 2.1 fixtures: each status maps to the correct kind, a 502 then a 200 succeeds, a 401 is not retried, and a timeout gives a network error.
- [x] 2.6 Add the debug request log (an httpx event hook through `redact.py`). Verify with a test that debug output shows the method, team, status, and duration, and shows `Authorization` as redacted.

## 3. Output layer

- [x] 3.1 Implement `output.py`: table mode and JSON mode, the summary line, the empty-result message, JSON errors on stderr, `NO_COLOR` support, and no color when stdout is not a TTY. Verify with tests that JSON mode writes only valid JSON to stdout, and that piped output has no ANSI escape codes.
- [x] 3.2 Implement the top-level exception handler. It renders a tool error with target and hint, maps the exit code, and shows a traceback only with `--debug`, after redaction. Verify with tests that an unexpected exception exits with 1, with no traceback unless `--debug` is set.
- [x] 3.3 Build the CLI skeleton from design D9: one Typer sub-app for each noun, global options on the root, and the plural-noun handler. Verify with tests: `fcm sites` exits with 2 and suggests `fcm site list`, `fcm site show --json` with no target exits with 2, and a test that walks the command tree asserts that every command is `<noun> <verb>` with a verb from the fixed set.
- [x] 3.4 Implement `cli/picker.py` from design D10: interactive-mode detection (stdin and stdout are TTYs, no `--json`), a `questionary` search-filter select whose entries show name, team title, and bench title, cancel mapped to exit 2, and a usage error with the candidate list in non-interactive mode. Verify with tests: the picker is never called when stdout is piped or `--json` is set, a cancel exits with 2, and the non-interactive error lists each candidate's name, title, and team.

## 4. Credential profiles

- [x] 4.1 Implement `config.py`: the TOML read and write at the platformdirs path with mode `0600`, `default_profile`, and `base_url` for each profile. Verify with tests (on a temp dir) that the file round-trips, has mode `0600`, and never contains key or secret fields.
- [x] 4.2 Implement `credentials.py`: keyring storage as one JSON entry for each profile, detection of an unusable backend (fail backend or plain-text backend), the `FCM_API_KEY` / `FCM_API_SECRET` override, the single-variable error, and profile selection (`--profile`, then `FCM_PROFILE`, then the default). Verify with tests that use an in-memory keyring backend, for each scenario in the credential-profiles spec.
- [x] 4.3 Implement `fcm profile add` (hidden secret prompt, `--base-url`, `--replace`, verify through `account.get` before the store). Verify with tests: valid credentials store and print the user and team count, rejected credentials store nothing, a duplicate name without `--replace` is refused, and the secret is never an argument.
- [x] 4.4 Implement `fcm profile list`, `fcm profile test`, and `fcm profile remove` (with a confirmation prompt). Verify with tests: `list` shows no credential characters, `test` reports the teams or an auth error with the `--replace` hint, and `remove` deletes the config entry and the keyring entry only after confirmation.
- [x] 4.5 Write the README sections "Install", "Add a profile", and "Credentials and security" (keyring, env fallback, what the config file holds, read-only scope). Verify that each documented command runs as written against a mocked or real profile.

## 5. Inventory

- [x] 5.1 Implement team discovery in `inventory.py` from `account.get` `teams`, so both the dict form and the plain-string form parse. Verify with tests on fixtures for both forms.
- [x] 5.2 Implement the team fan-out (4-worker pool), the per-team result or error collection, deduplication by name, and owning-team attribution (D5). Verify with `respx` tests: 3 teams with one permission error return rows from 2 teams plus one named failure, and duplicate child-team rows appear once.
- [x] 5.3 Implement the resolvers for team, bench, and site from design D10 (exact name, then exact case-insensitive title; `Resolved`, `Ambiguous`, or `NotFound` with up to 5 close matches). Verify with unit tests for each scenario in the cloud-inventory "Resolve a team, bench, or site by name or title" requirement.
- [x] 5.4 Implement `fcm team list`. Verify with a test that it lists name and title for each discovered team, in table mode and in JSON mode.
- [x] 5.5 Implement `fcm bench list [--team]` with the spec columns, `--team` resolved by name or title, the unknown-team error, and exit code 7 on partial failure. Verify with tests for the all-teams, single-team, team-by-title, unknown-team, and partial-failure scenarios.
- [x] 5.6 Implement `fcm site list [--team] [--bench] [--status]`, with `--status` mapped to `site_filter`, and `--bench` resolved by name or title and then filtered on the client side on `group`. Verify with tests for each filter, for an ambiguous bench title (picker on a TTY, exit 2 when piped), and for the empty-result message.
- [x] 5.7 Implement `fcm site show [SITE] [--team]`: resolve the site across the teams in scope, open the picker when the site is missing in interactive mode, then call `site.get` and `site.installed_apps`, and render the detail and the apps table. Verify with tests: site found, team found automatically, picker used when the site is missing on a TTY, exit 2 when the site is missing with `--json`, and not found exits with 5.
- [x] 5.8 Write the README section "Commands", with one example for each inventory command, the name-or-title rule, the picker behavior, and the exit-code table. Verify that the examples match the real `--help` output.

## 6. Integration checks

- [x] 6.1 Add a secret-leak test suite with a canary key and secret. It runs every command through each error path (auth, permission, not-found, 5xx, timeout, non-JSON body, unexpected exception), with and without `--debug` and `--json`. Verify that the canary never appears in stdout or stderr.
- [x] 6.2 Add a test that walks every CLI command with `respx` in strict mode, and asserts that only allowlisted methods are requested. Verify that the test fails if a command calls a method that is not on the allowlist.
- [x] 6.3 Run a manual smoke test with a real profile: `profile add`, `team list`, `bench list`, `site list --bench`, `site show`, and `profile remove`. Verify the output by eye against the FC dashboard, and record the result in the change notes.

## 7. Smoke-test fixes

- [x] 7.1 Team label from the owner email when titles are shared, `team list` Owner column, and `--team` matching the owner email. Verify with tests for unique titles, a shared title, and `--team <owner email>`.
- [x] 7.2 Raise the fan-out limit to 8 workers. Verify with a test that 13 teams run with 8 workers at most.
- [x] 7.3 Partial `site show` when FC denies the detail. Verify with tests in table mode and JSON mode: known fields shown, the "not permitted" line, and exit code 4.
- [x] 7.4 Permission hints that name the team owner and fit the command. Verify with tests for `site show` and for a single-team list.

## Smoke test notes (2026-11-09)

- Profile: environment credentials through `bin/fcm-dev` (no unlocked keyring on the dev host).
- `team list`: 13 teams, 2.0 s. `bench list`: 46 benches, 2.3 s. `site list`: 64 sites, 5.4 s.
- `site list --bench` by title: correct sites; a shared title gave exit 2 with owner-labelled candidates.
- `site show`: full detail in 3 of 5 tested teams; partial view with exit 4 in the 2 teams that deny detail.
- The maintainer checked the counts against the FC dashboard: all correct.
- `profile add` and `profile remove` ran in tests only (in-memory keyring), not against a real keyring.
- The smoke test found 4 issues. Group 7 fixed them.

## Workflow follow-up

- Run `./bin/openspec validate read-only-core --strict` before archive.
- Archive the change with `/opsx:archive` after review.
