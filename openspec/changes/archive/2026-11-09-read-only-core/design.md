# Design

## Context

The repository is empty apart from OpenSpec scaffolding. See proposal.md (Why) for the motivation. The specs under `specs/` define the behavior. This document covers how to build it.

Facts about the FC API, from the FC docs and the `frappe/press` source (read 2026-11-09):

- Every request needs `Authorization: Token <key>:<secret>`. A request for one team also needs `X-Press-Team: <team>`. One key belongs to one FC user and reaches every team that the user is a member of.
- The URL form is `https://cloud.frappe.io/api/method/<dotted.path>`. FC moved the API from `frappecloud.com`; the old host answers every call with `308 Permanent Redirect` (seen 2026-11-09). A guest call to the new host returns HTTP 403 with a standard Frappe error body (`exc_type`, `_server_messages`).
- `press.api.account.get` returns `teams`, a list of `{name, team_title, user}`. Only enabled teams are in the list. The server caches the result for 60 s for each user. In one edge case, the entries are plain name strings, so the parser must accept both forms.
- `press.api.bench.all(server=None, bench_filter=None)` lists the release groups of the current team and its child teams. Each row has `name`, `title`, `version`, `status`, `number_of_sites`, `number_of_apps`, and `tags`. Rows do not include `team`.
- `press.api.site.all(site_filter=None)` lists the sites of the current team and its child teams. Each row has `name`, `status`, `bench`, `group`, `version`, `team`, `server_region_info`, `tags`, and `update_available`. FC has no filter for the release group, so the tool filters on `group` on the client side.
- `press.api.site.get(name)` returns the site detail without apps. `press.api.site.installed_apps(name)` returns the apps.
- The list endpoints take no team argument. They use the current team of the request. The source of the current team (`get_current_team`) was not read, so the assumption that it reads `X-Press-Team` is not confirmed. Task 2.1 confirms it.
- The FC docs do not describe error bodies. The tool assumes the standard Frappe framework error response. Task 2.1 confirms it.

Constraints:

- The repository will be public. No secret can appear in the repository, the config file, the output, or a log.
- Later changes add write actions (deploy, app install) and a TUI. Both must reuse this core without a rewrite.

## Goals / Non-Goals

**Goals:**

- A layered core (credentials, API client, inventory service) that has no dependency on the CLI. A later TUI calls the same service.
- A read-only boundary that the code enforces, not only a convention.
- Tests that prove no secret leaks, on every error path.

**Non-Goals:**

- Any FC write method. This includes deploy, app install, restart, and team switch on the server (`press.api.account.switch_team`).
- A local cache of inventory data. FC already caches `account.get` for 60 s, and inventory sizes are small.
- An audit log. This change has no actions to audit. The action-pipeline change adds the audit log.
- Windows-specific testing. The code uses portable libraries, but CI covers Linux and macOS only.

## Decisions

### D1. Layers

```
cli/  (Typer commands, argument parsing)      <- later: tui/ on the same service
  |
  v
inventory.py   (team fan-out, filters, partial-failure collection; returns dataclasses)
  |
  v
api/client.py  (FCClient: auth, X-Press-Team, allowlist, retries, error mapping)
  |
  v
credentials.py (profile resolution: --profile, FCM_PROFILE, default; keyring or env)
config.py      (TOML config, no secrets)
redact.py      (one redaction helper used by logging, errors, and debug output)
output.py      (tables / JSON / error rendering / exit codes)
```

The CLI layer only parses arguments and renders. Business logic lives in `inventory.py`, so the TUI can reuse it. Alternative: put the logic in the CLI commands. That is faster now, but the TUI change would then need a rewrite.

### D2. Libraries

| Need | Choice | Why | Alternative not chosen |
| --- | --- | --- | --- |
| HTTP | `httpx` (sync) | Timeouts, transport hooks, and `respx` for test mocks | `requests` (weaker mock and hook story) |
| CLI | `typer` | Typed options, help text, and it uses Click | `argparse` (more boilerplate), raw `click` |
| Tables, color | `rich` | Tables, `NO_COLOR` support, and Textual (likely TUI library) uses it | `tabulate` (no color or TTY detection) |
| Secrets | `keyring` | Uses the native OS store on Linux, macOS, and Windows | Encrypted file (the tool must then manage a master key) |
| Config dir | `platformdirs` | Gives the correct path on each OS | Hard-coded `~/.config` |
| Config write | `tomllib` (read) + `tomli-w` (write) | TOML is readable, and Python reads it with no extra package | JSON (no comments), YAML (larger dependency) |
| Picker | `questionary` | Type-to-filter select, maintained, uses `prompt_toolkit` (see D10) | `InquirerPy`, `iterfzf` |
| Tests | `pytest` + `respx` | Standard tools | - |
| Lint | `ruff` | One fast tool for lint and format | - |

The project uses `uv` and a `pyproject.toml` with a `src/` layout. The minimum version is Python 3.11, because `tomllib` arrived in 3.11. The console script is `fcm`.

### D3. Credential storage

- The keyring uses service name `fc_manager`, with one entry for each profile. The entry username is the profile name. The value is a JSON string `{"api_key": ..., "api_secret": ...}`. One entry keeps the key and the secret consistent, because one write changes both.
- The config file is `platformdirs.user_config_dir("fc_manager")/config.toml`. It holds `default_profile` and, for each profile, `base_url`. The tool creates it with mode `0600`.
- If the keyring backend is the `fail` backend or a plain-text backend, the tool treats the keyring as unavailable. The tool then refuses to store credentials and points to `FCM_API_KEY` / `FCM_API_SECRET`. This matters on headless Linux servers with no Secret Service.
- Credentials live in memory in a small class whose `__repr__` and `__str__` show `***`. An accidental print or a traceback local-variable dump then shows no secret.

### D4. Read-only allowlist

`FCClient` holds a frozen set of allowed method paths:

```
press.api.account.get
press.api.bench.all
press.api.site.all
press.api.site.get
press.api.site.installed_apps
```

`FCClient.call(method, team=None, **params)` raises `MethodNotAllowed` before any I/O when `method` is not in the set. Requests use HTTP GET, with complex params (`site_filter`, `bench_filter`) sent as JSON strings. A later change adds write methods through a separate, explicit path that the action pipeline gates. That later change does not grow this set by accident. Alternative: rely on code review only. That fails silently, so it is not chosen.

### D5. Team fan-out

`inventory.py` reads the team list once for each run through `account.get`. A command with no `--team` calls the list endpoint once for each team, with `X-Press-Team` set. The calls run in a `ThreadPoolExecutor` with at most 8 workers (the smoke test measured about 1.8 s per `site.all` call; 13 teams took 7.7 s with 4 workers), so a user with many teams does not wait for each team in turn. Each team result is either rows or an error. The service returns both lists, so the CLI can show rows and failures together (exit code 7).

Deduplication: `bench.all` and `site.all` include child teams. A row can therefore appear under its parent team and under its own team. The service removes duplicates by `name`. The service keeps the owning team from the row's `team` field (sites) or from the team of the request (benches).

### D6. Error mapping

The tool assumes standard Frappe error responses. Task 2.1 confirms this assumption.

| HTTP status / `exc_type` | Tool error kind | Exit code |
| --- | --- | --- |
| 401, `AuthenticationError` | authentication | 3 |
| 403, `PermissionError` | permission | 4 |
| 404, `DoesNotExistError` | not found | 5 |
| 417, `ValidationError` | validation | 1 |
| 429 | rate limit | 6 |
| 5xx, connect error, timeout | server / network | 6 |

The FC message comes from `_server_messages` (a JSON string that holds a list of JSON strings, each with `message`). The `message` field or `exception` is the fallback. The tool strips HTML tags from the message. A response that is not JSON gives an error with the HTTP status and the first 200 characters of the body. The tool passes that text through `redact.py` first.

Redirects: the client never follows a redirect, because the `Authorization` header must not go to a host that the user did not choose. A 3xx response to another host is a usage error (exit 2) that names the new host and gives the fix (`fcm profile add <name> --base-url <new host> --replace`). Any other redirect is a server error.

Timeout: 10 s connect, 30 s read. Retry: at most 2 times, only after a network error or a 5xx response, with a backoff of 0.5 s and then 1.5 s.

### D7. Redaction

`redact.py` holds a registry of secret strings, filled when credentials load. It also has a function that replaces each registered string and any `Authorization: ...` value with `***`. The following paths all go through this function:

- the error renderer,
- the debug request log (written by `FCClient` around each request, so one place sees the method, team, status and duration),
- the top-level exception handler, which prints the traceback only with `--debug`.

A test fixture loads a canary key and secret. The test then runs each error path (auth, permission, 5xx, timeout, non-JSON body, unexpected exception) and asserts that the canary does not appear in stdout or stderr.

### D8. Output

`output.py` decides the mode once: `json` if `--json`, else `table`. Rich turns off color when the output is not a TTY or when `NO_COLOR` is set. Table columns follow the cloud-inventory spec. In JSON mode, stdout holds only data, and errors go to stderr as `{"error", "kind", "hint", "target"}`. Each tool error carries its exit code, so one place in the top-level handler maps the error to the exit code.

### D9. Command grammar

The cli-output spec fixes the grammar `fcm <noun> <verb> [TARGET] [options]`. The CLI has one Typer sub-app for each noun (`profile`, `team`, `bench`, `site`), and each verb is a command in that sub-app. The shared options (`--profile`, `--json`, `--debug`) sit on every command, not on the root app, so they work after the verb as in `fcm bench list --json`. The top-level error handler reads `--json` and `--debug` from the raw arguments, so errors raised before a command runs still use the right format. `--team` sits on each command that is scoped to a team, so `fcm profile list --team x` is a usage error and not a silent no-op.

A small handler catches an unknown root command that is a plural noun (`sites`, `benches`, `teams`, `profiles`). It exits with 2 and suggests the singular `list` form. The tool provides no aliases, because each alias is one more name to keep consistent when write actions arrive.

The rule for later write actions, recorded here so the action-pipeline change follows it: the noun is the resource that FC changes. An app install changes a site, so the command is `fcm site install-app <site> <app>`, not `fcm app install`. A deploy changes a bench, so the command is `fcm bench deploy <bench>`. Action verbs are kebab-case and go through the PLAN, PREVIEW, and CONFIRM pipeline. Alternative not chosen: verb-noun (`fcm list sites`, like kubectl). With verb-noun, the help for one resource is spread over many verbs, and `fcm site --help` cannot show everything that a user can do to a site.

### D10. Target resolution and the picker

FC names are often not human-readable (team ids, `bench-NNNN`), so the user can type either the name or the title. The specs fix the rules: exact name first, then exact case-insensitive title; one match resolves, more than one is ambiguous.

- **Resolver** (`inventory.resolve_*`): a pure function over the already-fetched team, bench, or site lists. It returns `Resolved(item)`, `Ambiguous(candidates)`, or `NotFound(close_matches)`. Close matches come from `difflib.get_close_matches` over names and titles, at most 5. The resolver sits in the service layer, so the TUI reuses it. It never prompts.
- **Picker** (`cli/picker.py`): the CLI layer turns `Ambiguous` or a missing target into a prompt only in interactive mode (stdin and stdout are TTYs, no `--json`). Otherwise the CLI raises a usage error (exit 2) with the candidate list.
- **Library**: `questionary`, with `select(..., use_search_filter=True)` for type-to-filter. It is maintained, small, and uses `prompt_toolkit`. Alternatives not chosen: `InquirerPy` (fuzzy prompt, but no release for a long time) and `iterfzf` (needs the external `fzf` binary).
- **Flat, not step-by-step**: for a site, the picker shows one list over all teams, with each entry as `site  - team title / bench title`. A step-by-step walk (team, then bench, then site) costs more keystrokes. It is reserved for the later write actions, where the next choice depends on the earlier one, for example "pick bench, then pick the app to deploy".
- **No sticky context**: the tool has no `fcm use team ...` state. A saved target can send a later deploy to the wrong client, so each command names or picks its target.
- **Team label**: the FC default title "Parent Team" is common, so titles often do not tell teams apart (the smoke test found 13 teams, 1 title). `account.get` gives each team's owner email in `user`. The service sets each team's display label once: the title when it is unique, else the owner email, else the name. All output (Team column, picker entries, errors) uses that label. `--team` also matches the owner email.
- **Denied detail**: FC can allow `site.all` but deny `site.get` and `site.installed_apps` to a member role (seen in 2 of 5 client teams). `site show` then renders the fields from the site row it already has, adds a "not permitted for your role" line, and exits 4. Permission hints name the team owner.
- **Cost**: a picker for sites needs the site list of every team first. It uses the D5 fan-out. With `--team`, only that team is fetched.

## Risks / Trade-offs

- [The `X-Press-Team` header does not set the current team for the list endpoints] -> Resolved by the 2.1 spike (2026-11-09, 13 teams): the header selects the team for `site.all`. Task 2.1 checked this with a live key before the inventory work starts. The fallback is to call `press.api.account.switch_team` for each team. That changes server session state, so the user must approve it before the tool uses it.
- [FC ignores an unknown or no-longer-allowed `X-Press-Team` and answers HTTP 200] -> Confirmed by the 2.1 spike: a made-up team name returns HTTP 200 with **no rows**. FC does not fall back to the default team, so no row gets the wrong team label. The remaining effect: a team you lost access to inside FC's 60 s `account.get` cache shows as empty, not as an error. That is acceptable for a read-only listing.
- [FC answers 403, not 404, for a site that does not exist] -> Seen in the 2.1 spike (`site.get` on an unknown name). `fcm site show` resolves the site from the site list first and reports "not found" (exit 5) itself, so users see the right error. A 403 maps to "permission" only when a site disappears between the list call and the `site.get` call.
- [`account.get` returns the user's own `api_key` in its body] -> Seen in the 2.1 spike, where the fixture guard refused to write it. `fcm` keeps only the user and the teams from this response and never prints response bodies, and the key is a registered redaction value. The spike script masks every field whose name contains `key`, `secret`, `token` or `password`, and keeps only `user` and `teams` from `account.get`.
- [The FC error body differs from the Frappe standard] -> Task 2.1 records real error bodies as test fixtures. The parser keeps a generic fallback (HTTP status plus a short body).
- [The FC API is not a public, versioned contract] -> All endpoint knowledge stays in `api/client.py` and the response parsers. Parsers ignore unknown fields and use defaults for missing fields. Recorded fixtures make a break show up in tests.
- [No keyring on a headless server] -> The tool falls back to environment variables, which is explicit and documented. The tool never writes a plain-text file.
- [A secret leaks through a new code path] -> The central redaction helper, the masked credential class, and the canary tests reduce this risk. The README asks contributors to route all output through `output.py`.
- [Fan-out over many teams reaches an FC rate limit] -> The pool has at most 8 workers. A 429 response maps to a clear error. The read endpoints show no rate limit in the source today.

## Migration Plan

This change has no migration, because it is the first release. Rollback means: uninstall the package and delete the config file and the keyring entries (`fcm profile remove`).

## Open Questions

- The command name `fcm` is an assumption. A rename touches only `pyproject.toml` and the docs.
- The package name on PyPI, if the project gets published, is not decided. Publication is out of scope here.
