# Design

## Context

`fcm` has 3 write actions: `bench-deploy`, `site-migrate` and `site-update`. The menu has an `Action` registry, a site step with an optional filter, and a migrate watch that finds an FC job of a site through `press.api.site.running_jobs`. This change adds 2 more write actions on the same parts.

FC facts from the press source (`frappe/press` `master`, read on 2026-11-09):

- `press.api.bench.all_apps(name)`, `@protected("Release Group")`. It returns the published marketplace apps that the release group does not have. Each row has `name` (Marketplace App), `title`, `image`, `app` (app name), `description`, `sources`, `repo`, `total_installs`, and `no_public_releases` when the app has no public source at all. `sources` holds the enabled public App Sources for the Frappe version of the group: `name`, `branch`, `repository`, `repository_owner`, `app`, `version`. An empty `sources` means "not compatible with this version".
- `press.api.bench.add_app(name, source, app)` calls `add_apps`, which calls `ReleaseGroup.update_source`. That appends `{source, app}` to the group apps and saves the group. It returns nothing and starts no job. The app reaches a bench only through the next deploy.
- `press.api.bench.add_apps(name, apps)` takes a list of `{app, source}` and calls `update_source` for each. One request adds several marketplace apps.
- The dashboard adds a GitHub app with `press.api.client.run_doc_method(dt="Release Group", dn, method="add_app", args={"app": {name, title, repository_url, branch, github_installation_id}})`. `ReleaseGroup.add_app` creates the App when it is new, checks the Frappe version of the branch, adds an App Source for the team, and calls `update_source`. It takes one app.
- GitHub reads (spike question 7, 2026-11-09): `press.api.github.options` returns `authorized` and `installations` (`id`, `login`, `url`, `image`, `repos` with `id`, `name`, `private`, `url`, `default_branch`); 5 installations in 5.8 kB for the test team. `press.api.github.branches(owner, name, installation)` returns the GitHub branch rows (356 for `frappe/crm`). `press.api.github.app(owner, repository, branch, installation)` returns `{name, title, frappe_version}`, for example `{"name": "crm", "title": "Frappe CRM", "frappe_version": ">=15.0.0,<17.0.0"}`. Without an installation, FC reads a public repository.
- FC has no marketplace search that works over GET: `press.api.client.search_link` takes a `filters` dict, and FC fails on a filters string over GET (spike of 2026-11-09). The search must run in `fcm`.
- `press.api.site.available_apps(name)`, `@protected("Site")`. It returns the App Sources of the site's bench whose app the site does not have: `name` (source), `app`, `repository_url`, `repository_owner`, `branch`, `team`, `public`, `app_title`, `title` (marketplace title, can be null). A marketplace source also has `billing_type`, and `has_plans_available` with `plans` when FC has plans for the Frappe version.
- `press.api.site.install_app(name, app, plan=None)` calls `Site.install_app`, `@site_action(["Active"])`. With a plan, FC checks that the team can buy a paid app. When the site already has the app, FC returns nothing and starts no job. Otherwise FC creates the agent job `Install App on Site`, logs a site activity, sets the site to Pending, and adds marketplace config. The API function returns nothing (the job name is not passed back).
- `press.api.site.running_jobs` and `press.api.site.job` already work over GET with a plain name (migrate spike, 2026-11-09).

## Goals / Non-Goals

**Goals:**
- `fcm bench-add-app` and `fcm site-install-app`, with the same safety as the other writes: allowlist, preview, typed confirmation, one POST, no retry.
- 2 menu entries, and a "Deploy now?" step after an add from the menu.
- Reuse of the migrate job watch for the install job, with no change to the migrate behavior.

**Non-Goals:**
- Private GitHub apps, team apps that are not on the marketplace, and several apps in one request.
- Remove and uninstall.
- Marketplace plans and billing.
- Branch changes of an app that the group already has.

## Decisions

### D1. App is an option, not a second positional argument
The `cli-output` spec says that a command has one positional target. The bench or the site is the target. The app is given with `--app <app name>`, and a bench source with `--source <source name>`. With no `--app` in interactive mode, the app step asks. In a script, a missing `--app` exits with code 2.
- Alternative: `fcm bench-add-app <bench> <app>`. Rejected: it breaks the one-target rule, and a script reader cannot tell which argument is which.

### D2. Command names carry the object
`bench-add-app` and `site-install-app`. `cli/root.py` keeps one split rule: the noun is the text before the first hyphen, the verb is the rest. `WRITE_VERBS` gets `add-app` and `install-app`. `test_cli_core.py` keeps its check, which already splits at the first hyphen. The old two-word guard in `FcmGroup` still works: `fcm bench add-app` resolves to `bench-add-app` in `self.commands`, so the user gets the hyphenated name.
- Alternative: `bench-add` and `site-install`. Rejected by Riz on 2026-11-09: `add` means a local profile today.

### D3. One service module for both actions
New `src/fc_manager/apps.py` with no CLI dependency:
- dataclasses `MarketApp` (app, title, sources, compatible), `AppSource` (name, branch, repository), `AddPlan` (bench, version, app, source); `SiteApp` (app, title, branch, source, has_plans), `InstallPlan` (site, status, app).
- parsers `parse_all_apps()` and `parse_available_apps()` that tolerate missing fields. The title falls back from `title` to `app_title` to `app`. The repository is `repository_owner/repository`, or the path of `repository_url`.
- `AppService.offered_apps(bench)`, `pick_app()`, `pick_source()`, `add(plan)` (the only bench write).
- `AppService.offered_site_apps(site)`, `check_site(site)`, `install(plan)` (the only site write), `watch_install(plan, sleep, ...)`.

### D4. Shared site job watch
The migrate watch already finds a job by type in `running_jobs`, then polls `site.job` until Success or Failure. This change moves that loop into `migrate.py` as `watch_site_job(service, site, job_type, unknown_error, failed_error, ...)`. `MigrateService.watch()` calls it with `"Migrate Site"`, and `AppService.watch_install()` with `"Install App on Site"`. The migrate tests stay as they are and must pass with no change. New errors `InstallFailed` (exit 8, with `step`) and `InstallUnknown` (exit 6).
- Alternative: copy the loop. Rejected: 2 copies of a timing-sensitive loop drift apart.

### D5. Install check reuses the migrate check
`check_site()` reads the site status and the running jobs, as `MigrateService.check()` does, with the allowed statuses `("Active",)`, which is the `@site_action` of `Site.install_app`. The busy-job check is the same. Because the check refuses a site with a job in progress, the first `Install App on Site` job that shows up after the request is the one this request made.

### D6. No plan is ever sent
`install()` sends `{name, app}` only. An app with `has_plans_available` is not pickable in the app step, and `--app` with such an app exits with code 2 (decision by Riz, 2026-11-09). This keeps billing out of `fcm`. A free plan is also refused, because fcm does not read plan prices.

### D7. Add result is the FC answer
FC starts no job for an add. A 2xx answer means that the group record is saved. The command prints the result and the hint `fcm bench-deploy <bench>`, and exits with code 0. A timeout or 5xx raises `WriteUnknown` through `WRITE_FOLLOW_UP`: `add_apps` and `run_doc_method` map to `("add-app", "bench-show")`, and `install_app` to `("install", "site-show")`. For `run_doc_method` the hint uses `dn`, because the body has no `name`.

### D11. Marketplace search (revised after the first menu check, 2026-11-09)
The first build showed all 388 apps in one list. The revised step is a search:
- **One read.** `all_apps` is read once per bench and session, and kept in `AppService` (a dict keyed by bench name). The menu keeps one `AppService` per session, so a second "Add an app" on the same bench sends no request.
- **Index once.** `SearchIndex` holds, for each compatible app: the lowercase app name, the lowercase title, and the words of both (split on space, `_`, `-`). Not compatible apps are left out.
- **Rank.** For a query `q` (lowercase, trimmed), each app gets the best of these ranks: 0 exact app name; 1 app name starts with `q`; 2 a word starts with `q`; 3 `q` is inside the name or title; 4 the letters of `q` appear in order in the name. No match: the app is left out. Ties sort by the rank position of the match, then by the title. `search(q, limit=10)` uses `heapq.nsmallest`, so it does not sort the full list. An empty query returns no rows.
- **Prompt.** `picker.search()` wraps `questionary.autocomplete` with a prompt_toolkit `Completer` that calls `index.search(text)`. The dropdown shows at most 10 rows. Enter on a row picks it. The search costs O(apps x query length) per key press on about 200 rows, and sends nothing to FC.
- **Several apps.** After each pick, the step shows the picked apps and asks "Add another app?" (default No). Then the source step for each app with more than one source, one preview, and one `add_apps` POST.
- Alternative: keep the select list with its filter. Rejected by Riz: it prints the whole list, and its filter is a substring match only.

### D12. GitHub add
- **Repository.** `github.options` lists the installations and their repos. The step lists `login/name` for each repo, plus "Paste a public GitHub URL". A pasted URL or `--repo` must match `https://github.com/<owner>/<repo>` (an optional `.git` is removed); else exit 2.
- **Branch.** `github.branches(owner, name, installation)`; the default branch first, then `version-*`, then the rest. The step uses the search prompt of D11 on the branch names, because a repository can have hundreds of branches.
- **App.** `github.app(owner, repository, branch, installation)` gives the name, the title and the Frappe version range. When `apps` of the bench (from `bench.apps` of `deploy_information`, already read by `bench-show`) has that name, exit 2.
- **Write.** One `run_doc_method` with `dt="Release Group"`, `dn=<bench>`, `method="add_app"`, `args={"app": {...}}`. `FCClient.write()` refuses `run_doc_method` for any other `dt` or `method` (`WRITE_DOC_METHODS = {("Release Group", "add_app")}`), the same pattern as `READ_DOCTYPES`.

### D8. CLI module
New `src/fc_manager/cli/apps.py` with `add_app_to_bench(s, bench, opts, *, in_menu, path)` and `install_app_on_site(s, site, opts, *, in_menu, path)`, plus the 2 Typer commands. The bench walk reuses `deploy._pick_bench`. The site walk reuses `inventory.walk_to_site`. The preview, the confirmation and the JSON shape follow `cli/migrate.py` and `cli/deploy.py`. The install watch uses `migrate.watch_view`.
- `bench-add-app` options: `--app`, `--source`, `--confirm`, `--dry-run`, `--team`, `--json`, `--debug`, `--profile`.
- `site-install-app` options: `--app`, `--confirm`, `--dry-run`, `--no-wait`, `--team`, `--json`, `--debug`, `--profile`.

### D9. Menu
2 new `Action` entries: "Add an app (bench-add-app)" after "Deploy app updates", scope `bench`; "Install an app (site-install-app)" after "Update a site", scope `site`, no site filter. After a successful add in the menu, `add_app_to_bench` returns True, and the action asks `picker.ask_yes_no("Deploy now?", default=False)`. A yes calls `deploy.deploy_bench(s, bench, DeployOptions(), in_menu=True, path=path)`. `picker.ask_yes_no` is new: it wraps `questionary.confirm` with the picker style, and Esc means no.

### D10. Spike question 6
`scripts/fc_spike.py` gets question 6, read only:
- `press.api.bench.all_apps` for the first bench of the first team;
- `press.api.site.available_apps` for the first Active site.
New slim functions keep at most 20 rows and drop `image` and `description`. Private app names (not in `PUBLIC_APPS`) are replaced, and the anonymizer covers repository fields. Claude runs the spike with no `--write` first, reads the shapes, and then writes the fixtures `bench_all_apps.json` and `site_available_apps.json`. The install job fixture is synthetic and built from `site_job.json` with the job type `Install App on Site`.

## Risks / Trade-offs

- [The deploy after an add is not confirmed] The press source shows that the new app is in the group, but this change does not confirm that `deploy_information` lists it as an update. Mitigation: live check 8.2 runs "Deploy now?" up to the deploy preview, and checks that the new app is in the app step.
- [An install job can end between 2 polls] `running_jobs` shows only Pending and Running jobs. A short install that ends between 2 polls is not seen, and the result is "not known" (exit 6). Mitigation: the same as migrate; the hint names `fcm site-show`.
- [`all_apps` is large] FC returns every published marketplace app (388 rows, 151 kB on 2026-11-09). Mitigation: one read per bench and session, and a local ranked search (D11).
- [`github.options` is slow] FC calls GitHub for every installation and its repositories. Mitigation: it is read only when the user picks "From GitHub", and once per session.
- [The app check of a GitHub branch can fail] `github.app` throws when the branch has no `pyproject.toml` or no app in `hooks.py`. Mitigation: the FC message is shown, and nothing is written.
- [A free marketplace plan is refused] Some apps have only a free plan, and fcm still sends the user to the dashboard. Mitigation: the message is clear. A later change can read plan prices.
- [A failed install can leave the site Broken] FC sets the site to Pending, and an install failure can leave the app partly installed. Mitigation: the preview says that FC runs the install on the live site, and the result names the failed step and the final site status.

## Migration Plan

No data migration. The new commands are additive. Rollback is a revert of the commit.

## Open Questions

None. The names, the scope and the plan rule are decided (Riz, 2026-11-09).
