# Design

## Context

See proposal.md for the motivation. The current state:

- `read-only-core` is archived. The layers are cli -> inventory service -> `FCClient`. The client has one frozenset allowlist of 5 read methods and sends GET only. It retries network and 5xx errors at most 2 times.
- `Inventory.benches(teams)` fans out `press.api.bench.all` over the teams (8 workers, about 2.3 s for 13 teams). Each `Bench` carries its `Team`, so the team of a picked bench is known with no extra call.
- `cli/picker.py` has `is_interactive`, `choose` (single select, fuzzy filter), and `pick_or_fail`. Tests patch `picker.*` in one place.

The FC deploy API, read from the public `frappe/press` source (master, 2026-11-09). A read-only spike must confirm the response shapes before the code depends on them:

| Method | Kind | What it gives |
| --- | --- | --- |
| `press.api.bench.deploy_information(name)` | read | `update_available`, `deploy_in_progress`, `has_running_release_pipeline`, `apps[]` (`app`, `title`, `source`, `branch`, `current_hash`, `current_tag`, `current_release`, `releases[]`, `next_release`, `will_branch_change`, `current_branch`, `update_available`), `removed_apps[]`, `sites[]` (`name`, `server`, `bench`, `skip_failing_patches`, `skip_backups`), `last_deploy`, `number_of_apps` |
| `press.api.bench.deploy_and_update(name, apps, sites, run_will_fail_check)` | write | Starts the deploy. Returns a Release Pipeline name (new FC flow) or a Deploy Candidate name (old flow). |
| `press.api.bench.deploy_status(name)` | read | `is_validating`, `is_deploy_in_progress`, `candidate` |
| `press.api.client.get(doctype="Deploy Candidate Build", name)` | read | Build `status` (Draft, Scheduled, Pending, Preparing, Running, Success, Failure), `build_steps[]` (`stage`, `step`, `status`, `duration`, `cached`, `output`), `build_start`, `build_end`, `build_duration`, `build_error`, `deploy_candidate` |

The dashboard sends each app as `{app, source, release, hash}`, where `release` and `hash` come from the entry in `releases[]` whose name is `next_release` and that is not yanked. It sends each site as the full `sites[]` row from `deploy_information`. FC refuses a deploy unless the bench team is the current team (`X-Press-Team`), and refuses a second deploy while one runs.

## Goals / Non-Goals

**Goals:**
- A write path that is impossible to reach by mistake from a read command.
- A walk where each step costs at most 1 FC call after the bench pick.
- A deploy service with no CLI dependency, so that the later TUI reuses it.

**Non-Goals:**
- Cancel or stop a deploy on FC.
- A local audit log of deploys. It is a candidate for a later change.
- Support for the FC old deploy flow beyond the start call: when FC returns a Deploy Candidate name, the watch uses it directly.

## Decisions

### D1. Separate write path in the client

`FCClient` gets `WRITE_METHODS = frozenset({"press.api.bench.deploy_and_update"})` and a second method, `write(method, team, **body)`.

- `call()` (read) accepts `READ_ONLY_METHODS` only, as today. It now rejects a write method too.
- `write()` accepts `WRITE_METHODS` only, sends POST with a JSON body, and never retries. A timeout or a 5xx raises a new `WriteUnknown` error: "FC did not confirm the deploy. Its state on FC is not known." with the hint `fcm bench show <bench>`.
- `READ_ONLY_METHODS` gets `bench.deploy_information`, `bench.deploy_status`, and `client.get`. `client.get` reads any doctype that the user may see, so the client allows it only for the doctypes in `READ_DOCTYPES` (`Deploy Candidate Build`).

Alternative: one `call()` with a `write=True` flag. Rejected: a flag is easy to pass by mistake, and two methods make each call site show its intent. The strict respx walk test (from 6.2) extends to assert that only `bench deploy` ever sends POST.

### D2. Deploy service

New module `src/fc_manager/deploy.py`, with no typer or questionary import:

- Dataclasses `AppUpdate`, `DeploySite`, `DeployInfo`, `DeployPlan(bench, team, apps, sites, removed_apps)`, `DeployState(stage, build, status, steps, message)`.
- `DeployService(client)` with `info(bench) -> DeployInfo` (1 call), `plan(info, app_names, site_names) -> DeployPlan` (pure, no call, validates names), `start(plan) -> str` (the 1 write call), `state(bench, ref) -> DeployState` (1 or 2 read calls), and `watch(bench, ref, on_change, sleep)`.
- `plan()` builds the exact FC payload from the `DeployInfo` rows. It takes the release from `releases[]` where `name == next_release` and `is_yanked` is false. It never takes a release from user input.

### D3. Scoped queries

- Team step, then bench step (the maintainer changed the flat bench list to this on 2026-11-09): the team list comes from `account.get`, which the session already has, so it costs no new call. The bench step calls `bench.all` for the picked team only. With `--team`, the team step is skipped. With a BENCH argument, the fan-out still runs to find its team, because a bench row is the only source of the team.
- After the bench pick: every call carries the bench team. `info()` gives the apps and the sites in one call, so the app step and the site step need no more FC calls. The preview needs no call.

### D4. Walk and picker

- `picker.choose_many(prompt, options, default_selected)` wraps `questionary.checkbox` with search. The app step passes all apps as selected. The site step passes none.
- Esc on a step goes back one step: bench to team, apps to bench (same team), sites to apps. Ctrl+C before the confirmation cancels with exit 2.
- The site step is always shown. With no site on the bench, it prints "No active site on this bench: the deploy is bench only." and continues.

### D5. Preview and typed confirmation

- The preview is a rich panel built from `DeployPlan` only, so the preview and the request cannot differ.
- Interactive: `Type the bench title to deploy (<title>):`. The input must equal the title exactly (case and spaces). Anything else prints "Cancelled. Nothing was sent to FC." and exits 2.
- Non-interactive: `--confirm` must equal the bench FC name (an id, stable in scripts). There is no `--yes`.
- Why the title on a terminal and the name in scripts: a human reads the title in the preview, and a script already holds the id.

### D6. Progress watch

- After `start()` returns `ref`, poll every 2 s: `deploy_status(bench)` until it names a build, then `client.get` of that Deploy Candidate Build for the build steps, until a resting state (Success or Failure).
- Rendering: rich `Live` with one line per build step (pending, running, success, failure) on a terminal. With `--json` or no terminal: one JSON line per change on stdout, then a final result object.
- Ctrl+C: stop the loop, print "The deploy continues on FC. Run: fcm bench show <bench>", exit 130. No cancel call exists in this change.
- Site updates after the build: FC runs them as jobs after the bench is created. The build doc has no site jobs. After the build, the watch reads `deploy_information` again until no deploy runs, and reports each selected site from the site list of the bench.

### D7. Errors and exit code 8

- `DeployFailed(FcmError)` with `ErrorKind.JOB_FAILED` maps to exit 8. It carries the failed step and the FC message.
- A `BuildValidationError` or another validation error from `deploy_and_update` maps to the existing validation kind (exit 1). The FC message is shown as is. The "will fail" check is always on (`run_will_fail_check=true`).
- A permission error names the team owner, as in `read-only-core`.

### D8. `fcm bench show`

Read-only, in `cli/deploy.py` with `bench deploy` (both register on the `bench` group of `cli/inventory.py`). Calls: bench resolve (as today), then `deploy_information` and, when a deploy runs, `deploy_status` and the build through `client.get`. It reuses `DeployService.info()` and `state()`.

## Risks / Trade-offs

Spike findings (task 1.1, 2026-11-09, real bodies in `tests/fixtures/fc/`):

- `deploy_status.candidate` and `deploy_information.last_deploy.name` are Deploy Candidate Build names, not Deploy Candidate names. `press.api.bench.candidate` answers 403 for them. The watch reads the build through `client.get`, as the dashboard does.
- An app with no update has `update_available: null` (not `false`), `releases: []`, and `next_release == current_release`.
- `current_tag` and `release.tag` were `null` for every app. The version shown is the release tag when present, else the first 7 characters of the hash.
- `release.message` is the commit message. It can be long, and for a private app it can hold private text. The preview shows the first line only.
- Each `sites[]` row has `name`, `server`, `bench`, `skip_failing_patches`, and `skip_backups`, as the source showed.

- [The FC response shapes differ from the source read on 2026-11-09] -> A read-only spike recorded real anonymized `deploy_information`, `deploy_status`, and build bodies (see the spike findings above). The parsers accept missing fields.
- [FC switches between the old and new deploy flow (`use_new_deploy_flow`)] -> `start()` accepts either a Release Pipeline or a Deploy Candidate name. The watch always finds the candidate through `deploy_status`, which works for both.
- [A write times out after FC accepted it] -> No retry, `WriteUnknown` error, and the hint `fcm bench show`. A retry could start a second deploy.
- [A wrong bench or wrong sites] -> Scoped walk, preview built from the plan, typed title, no `--yes`, sites none by default.
- [The first real deploy is the first real write] -> Task 7.x runs it on a non-production bench that the maintainer picks, with no site selected (bench only).
- [`bench.all` also lists the benches of child teams, and its rows have no team field. `fcm` sends a deploy with the team under which it first saw the bench. If that is not the bench owner team, FC refuses with "Bench can only be deployed by the bench owner"] -> `fcm` shows the FC message and sends nothing more. Use `--team` with the owner team.
- [The build takes 10 to 30 minutes] -> `--no-wait`, Ctrl+C that leaves the deploy alone, and `fcm bench show` to look again.

## Migration Plan

No data migration. The change adds commands and one exit code. Rollback is a revert of the commit. A deploy that already started on FC continues on FC.

