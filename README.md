# fc_manager

`fcm` is a command-line tool to explore Frappe Cloud (FC) teams, benches and sites across
all the teams that your FC login can reach, to deploy app updates to a bench, and to
migrate or update a site.

Three commands change FC: `fcm bench-deploy`, `fcm site-migrate` and `fcm site-update`.
Each one shows a
preview of the target and the change, and starts nothing until you type the bench title or
the site name. Every other command is read-only.

## Install

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repository> fc_manager
cd fc_manager
uv sync
uv run fcm --help
```

To put `fcm` on your PATH, run `uv tool install .` from the repository root.

## Add a profile

A profile is one FC login. One login has one API key and one API secret, and it reaches
every team that the login is a member of. You do not list teams yourself; `fcm` finds them.

1. In the FC dashboard, open **Settings > Profile & Team > API Access** and create an API key.
   FC shows the secret one time only.
2. Add the profile. `fcm` asks for the key, and then for the secret in a hidden prompt:

   ```bash
   fcm profile-add work
   ```

   `fcm` checks the key with FC before it saves it, and prints your FC user and the number
   of teams it found.

Other profile commands:

```bash
fcm profile-list                  # names, default marker, base URL (never credentials)
fcm profile-test work             # check the key with FC, show the teams
fcm profile-add work --replace    # give a profile a new key
fcm profile-remove work           # asks for confirmation; --yes skips the question
```

The first profile you add becomes the default. To use another profile for one command,
pass `--profile <name>` or set `FCM_PROFILE`.

## Commands

Every command is one word, `fcm <noun>-<verb> [TARGET] [options]`, as in Frappe `bench
new-site`. A space always separates the command from an argument or an option. Nouns are
singular (`profile`, `team`, `bench`, `site`). There are no aliases: `fcm sites` and an old
two-word form (`site list`) tell you to use `fcm site-list`, and send nothing to FC.
`fcm --help` lists the commands in groups: Profile, Team, Bench, Site.

```bash
fcm team-list                                  # every team your login reaches
fcm bench-list                                 # benches (FC release groups) in all teams
fcm bench-list --team "ACME Corp"              # one team, by title or FC name
fcm site-list                                  # sites in all teams
fcm site-list --bench "ACME Prod"              # sites on one bench, by title or FC name
fcm site-list --status update-available        # active, inactive, broken, trial, update-available
fcm site-show erp.acme.com                     # one site with its installed apps
fcm site-show                                  # on a terminal: pick the site from a list
fcm bench-show "ACME Prod"                     # apps with updates, sites, a running deploy
fcm bench-deploy "ACME Prod"                   # deploy app updates (see below)
fcm site-migrate erp.acme.com                  # run bench migrate on one site (see below)
fcm site-update erp.acme.com                   # move a site to the newest bench (see below)
```

Options that work on every command:

| Option | Meaning |
| --- | --- |
| `--profile NAME` | Use this profile for this command. |
| `--json` | Write JSON to stdout. Errors go to stderr as one JSON object. Never prompts. |
| `--debug` | Show each FC request (method, team, HTTP status, time) and full tracebacks on stderr, with secrets masked. |

**Names or titles.** FC names are often generated ids, such as `bench-1234`. Wherever you
give a team or a bench, you can type its FC name or its title, as shown in the FC dashboard.
For a team, you can also type its owner email. `fcm` tries an exact name first, then the
owner email (teams only), then the title. Case does not matter for emails and titles.

**Team labels.** Many FC teams keep the default title "Parent Team". When 2 or more teams
share a title, `fcm` shows each team's owner email instead, in tables, pickers and errors.
`fcm team-list` shows the id, the title and the owner of every team.

**Picker.** On a terminal, when the target is missing (`fcm site-show`) or a title matches
more than one item (two benches called "Prod"), `fcm` shows a list you can filter by typing.
With `--json`, or when the output goes to a pipe or a script, `fcm` never prompts: it exits
with code 2 and lists the candidates.

**Partial failure.** When a command covers several teams and one team fails (for example,
your role in a client team does not allow it), `fcm` still shows the results from the other
teams, names the failed team, and exits with code 7.

**Limited roles.** In a client team, your role may allow FC to list a site but not show its
details. `fcm site-show` then shows what the site list already gave (team, bench, status,
version, region, update), says that details and apps are not permitted for your role, names
the team owner to ask, and exits with code 4.

### Menu: pick the bench once, then choose what to do

Run `fcm` with no command on a terminal to open the menu:

1. **Team**: pick a team (skipped when your login reaches one team only).
2. **Bench**: pick a bench of that team. `fcm` asks FC for that team's benches only.
3. **Action**: "Show bench (bench-show)", "Deploy app updates (bench-deploy)", "Migrate a
   site (site-migrate)", "Update a site (site-update)", "Pick another bench", or "Quit".
4. **Site** (site actions only): pick a site of that bench. The list shows only the sites
   of that bench, with their status. "Update a site" lists only the sites that have an
   update. Enter or Space picks the site under the pointer. When only one site is left,
   `fcm` picks it with no list and prints its name.

Every prompt shows the target path, for example `work > ACME Corp > ACME Prod (bench-1234)`,
and after a site pick `work > ACME Corp > ACME Prod (bench-1234) > erp.acme.com`. Each
action runs the same code as its command, so a deploy, a migrate or an update shows the
same preview and asks for the same typed confirmation. After an action ends, also with an
error or a cancelled confirmation, the action menu of the same bench opens again.

Esc goes back one step: site to action menu, action menu to bench, bench to team, team out
of `fcm`. Esc at the app step of a deploy goes back to the action menu. Ctrl+C at a menu
prompt ends `fcm` (exit 130). Ctrl+C during a deploy, migrate or update watch stops the
watch only, and the action menu opens again.
`fcm --profile NAME` opens the menu with that profile. Without a terminal, `fcm` prints the
help.

### Deploy app updates to a bench

`fcm bench-deploy` does what the FC dashboard deploy dialog does. On a terminal it walks
you through these steps:

1. **Team, then bench.** Give the bench by name or title, or pick it: first the team
   (shown by title or owner email), then a bench of that team. With `--team`, `fcm` skips
   the team step. After this step, every FC request goes to the team of that bench only.
2. **App updates.** No app is selected. Press Space on each app to deploy, then Enter.
3. **Sites.** The sites on the bench, **none selected**. With no site selected, the deploy
   goes to the bench only: the sites stay on the old bench, and FC shows "update
   available" for them. A backup is taken before each selected site is updated.
4. **Preview.** The profile, the team and its owner, the bench, each app from version to
   version, removed apps, and the sites or "Bench only".
5. **Confirm.** Type the bench title exactly. Any other input cancels, and nothing is sent.
6. **Progress.** `fcm` follows the build step by step until it ends. Ctrl+C stops the
   watch only: the deploy continues on FC. Run `fcm bench-show <bench>` to look again.

Esc goes back one step. When FC reports no update, or a deploy is already running on the
bench, `fcm` says so and sends nothing.

```bash
fcm bench-deploy --dry-run                              # pick team and bench, preview only
fcm bench-deploy bench-1234 --app erpnext --app hrms \
    --site erp.acme.com --confirm bench-1234           # in a script
fcm bench-deploy bench-1234 --all-apps --confirm bench-1234 --no-wait --json
```

Without a terminal (a script, a pipe or `--json`), `fcm` never prompts. You must give the
apps (`--app`, repeatable, or `--all-apps`), and `--confirm` with the bench FC name.
`--site` is repeatable; with no `--site`, the deploy is bench only. There is no `--yes`.
With `--json`, the progress is one JSON object per line.

Not in this version: in-place update, patch deploy, skipping backups or failing patches,
and an override of the FC "will fail" check. When FC refuses a deploy, `fcm` shows the FC
message and stops. Use the FC dashboard for those cases.

### Migrate a site

`fcm site-migrate` runs `bench migrate` on one site through FC, as the "Migrate" action in
the FC dashboard does. On a terminal it walks you through these steps:

1. **Site.** Give the site name, or pick it: team, then bench, then a site of that bench.
   A bench with one site skips the list.
2. **Checks.** `fcm` reads the site status and the FC jobs of the site. It stops, and sends
   nothing, when FC does not migrate a site in that status (FC migrates a site that is
   Active, Inactive or Broken), or when the site has an FC job in progress.
3. **Preview.** The profile, the team and its owner, the bench, the site and its status,
   and the patch mode: "Stop on a failing patch" (the default) or "Skip failing patches".
4. **Confirm.** Type the site name exactly. Any other input cancels, and nothing is sent.
5. **Progress.** `fcm` finds the new FC migrate job and follows its steps until it ends.
   Ctrl+C stops the watch only: the migrate continues on FC.
6. **Result.** "the site is migrated" (exit 0), or the failed step (exit 8). The result
   shows the site status on FC after the job. A failed migrate can leave the site Broken.

```bash
fcm site-migrate --dry-run                              # pick team, bench, site; preview only
fcm site-migrate erp.acme.com --confirm erp.acme.com    # in a script
fcm site-migrate erp.acme.com --confirm erp.acme.com --no-wait --json
```

Without a terminal, you must give the site and `--confirm` with the site name. There is no
`--yes`. `--skip-failing-patches` lets FC continue past a failing patch; the preview warns
about it, and the menu never turns it on. When no new migrate job shows up within 2
minutes after FC accepts the request, `fcm` says that the result is not known (exit 6).

### Update a site

`fcm site-update` moves one site to the newest bench of its bench group, as the "Update"
action in the FC dashboard does. FC takes the site down for the update and takes a backup
of the site first. On a terminal it walks you through these steps:

1. **Site.** Give the site name, or pick it: team, then bench, then a site of that bench
   that has an update. When only one site has an update, `fcm` picks it with no list.
2. **Checks.** `fcm` reads the FC update info, the site status and the FC jobs of the site.
   A site with no update ends here with exit 0, and nothing is sent. `fcm` stops, and sends
   nothing, when the site status is not Active or Inactive (this rule is stricter than FC:
   fix a Broken site first), or when the site has an FC job in progress.
3. **Preview.** The profile, the team and its owner, the bench, the site and its status,
   each app with an update and its current and next version (the release tag, else the
   short commit hash), a note for each app whose branch changes, and the patch mode.
4. **Confirm.** Type the site name exactly. Any other input cancels, and nothing is sent.
5. **Progress.** `fcm` follows the new FC update record and its steps until it ends. When
   the update fails, FC usually restores the site to the old bench; the watch shows that
   too. Ctrl+C stops the watch only: the update continues on FC.
6. **Result.** "the site is updated" with the new bench (exit 0). A failed update exits
   with code 8 and says what FC did: it restored the site to the old bench (Recovered), it
   could not restore the site (Fatal: contact FC support), or the update was cancelled.
   When the update stays failed for 10 minutes and FC starts no restore, `fcm` also exits
   with code 8. The result shows the site status on FC after the update.

```bash
fcm site-update --dry-run                              # pick team, bench, site; preview only
fcm site-update erp.acme.com --confirm erp.acme.com    # in a script
fcm site-update erp.acme.com --confirm erp.acme.com --no-wait --json
```

Without a terminal, you must give the site and `--confirm` with the site name. There is no
`--yes`, and there is no option to skip the FC backup. `--skip-failing-patches` lets FC
continue past a failing patch; the preview warns about it, and the menu never turns it on.
When FC does not confirm the request, or confirms it without the name of the update
record, `fcm` says that the update state is not known (exit 6).

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Unexpected error, or FC refused the request |
| 2 | Usage or configuration error (also: picker cancelled, missing target in a script) |
| 3 | Authentication error (FC rejected the key) |
| 4 | Permission error |
| 5 | Not found |
| 6 | Network, server or rate-limit error; also a result FC did not confirm (a write with no answer, a site update not confirmed in 30 minutes, a migrate job not found in 2 minutes, or an update with no record name) |
| 7 | Partial failure across teams |
| 8 | FC accepted a deploy, a migrate or a site update, but it failed on FC (a failed build step, migrate step or update, also when FC restored the site to the old bench) |

## Credentials and security

- **Keyring only.** `fcm` stores the API key and the API secret in the OS keyring (macOS
  Keychain, Windows Credential Manager, or the Secret Service on Linux). It never writes a
  secret to a plain file.
- **No keyring?** On a host with no secure keyring (for example a headless Linux server),
  `fcm profile-add` refuses to store anything. Set the credentials in the environment
  instead:

  ```bash
  export FCM_API_KEY=...       # both variables are needed
  export FCM_API_SECRET=...
  fcm team-list
  ```

  When both variables are set, they take precedence over the keyring for that run.
- **The config file holds no secrets.** It holds the profile names, the default profile and
  the base URL of each profile. Its location is the user config directory, for example
  `~/.config/fc_manager/config.toml` on Linux, with file mode `0600`.
- **The secret is never a command-line argument**, so it does not go into your shell history.
- **Redaction.** `fcm` masks the key, the secret and the `Authorization` header in all
  output, errors and `--debug` output.
- **HTTPS only.** A profile base URL must start with `https://`. TLS verification is always on.
- **Allowlists.** The HTTP client has a fixed allowlist of read-only FC API methods (GET)
  and a separate write allowlist with 3 methods (POST): `press.api.bench.deploy_and_update`,
  used only by `fcm bench-deploy`, `press.api.site.migrate`, used only by
  `fcm site-migrate`, and `press.api.site.update`, used only by `fcm site-update`. A call to
  any other method fails inside `fcm` before any request goes out. The generic FC document
  read (`press.api.client.get`) is allowed for 2 doctypes only: the deploy build and the
  site update record. The generic FC list read (`press.api.client.get_list`) is not allowed.
- **No retry of a write.** A deploy, migrate or update request is sent one time only. When FC does
  not confirm it (a timeout or a server error), `fcm` says that the result on FC is not
  known and tells you to run `fcm bench-show` or `fcm site-show`. A retry could start a
  second deploy, migrate or update.

To report a security problem, do not open a public issue. Contact the maintainer directly.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

**Dev credentials.** For day-to-day work on a host with no keyring, keep a dev key in a
git-ignored `.env` file:

```bash
cp .env.example .env
chmod 600 .env          # bin/fcm-dev refuses to run otherwise
$EDITOR .env            # fill in FCM_API_KEY and FCM_API_SECRET
./bin/fcm-dev team-list
```

`bin/fcm-dev` runs `uv run --env-file .env fcm ...`: uv puts the values into the
environment, and `fcm` reads them as normal environment variables. `fcm` itself never reads
a secret file. The file is plain text, so use a dev API key that you can revoke.

The FC API spike (`scripts/fc_spike.py`) uses the same file:

```bash
uv run --env-file .env python scripts/fc_spike.py
```
