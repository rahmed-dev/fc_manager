# Design

## Context

See proposal.md - Why. Current state:

- `cli/app.py` builds the root Typer group and mounts 4 sub-groups (`profile`, `team`, `bench`, `site`). `FcmGroup.resolve_command` turns a plural noun into a usage error.
- The command bodies of `bench show` and `bench deploy` (`cli/deploy.py`) open their own session, pick the bench with `_pick_bench` (team, then bench), and then do the work. The work and the pick are in one function, so another caller cannot run the work for a known bench.
- `cli/picker.py` gives `choose` and `choose_many`. With `back=True`, Esc raises `picker.GoBack`.
- The deploy walk raises `typer.Exit(130)` when the user stops the watch with Ctrl+C. A cancelled confirmation raises `UsageError` (exit 2).
- The tool has one user and no published release.

## Goals / Non-Goals

**Goals:**
- One registration point for commands, so that a new command is one decorator with its hyphenated name and its noun group.
- Show and deploy bodies callable with a session and a bench, by both the direct command and the menu.
- A menu loop that never ends `fcm` because of an action error.

**Non-Goals:**
- No shell completion change (completion stays off).
- No change to output formats, exit codes, or FC requests of any existing command.
- No generic plugin system for menu actions. The action list is a plain list in `cli/menu.py`.

## Decisions

### D1. Flat registration on the root group
All commands register on the root Typer app with their full name and a help panel: `@app.command("bench-list", rich_help_panel="Bench")`. A small module `cli/root.py` owns `app` and `FcmGroup`, so `profile.py`, `inventory.py`, `deploy.py`, and `menu.py` import it with no import cycle. `app.py` keeps `run()` and imports the command modules for registration.
- Alternative: keep the sub-groups and add hyphenated aliases. Rejected: it keeps two grammars, and the spec forbids aliases.
- Alternative: hyphen names with a custom Click group that splits on `-`. Rejected: more code for no user benefit.

### D2. Old-form and plural errors in `FcmGroup.resolve_command`
- `fcm sites` (plural) gives exit 2 with "Use: fcm site-list".
- `fcm bench list ...` (a noun, then a known verb) gives exit 2 with "Use: fcm bench-list".
- `fcm bench` (a bare noun) gives exit 2, and the hint lists the commands of that noun.

The check runs before any session opens, so nothing reaches FC. These errors are not aliases: the command does not run.

### D3. Menu entry through the root callback
The root app gets `invoke_without_command=True` and a callback with `--profile`. When no command is given: in interactive mode, the callback runs `menu.run(profile)`. In other cases, it prints the help and exits 0. The interactive test is `picker.is_interactive(json_mode=False)`, the same test as every other prompt.

### D4. Work functions split from the commands
`cli/deploy.py` gets `show_bench(s, bench)` and `deploy_bench(s, bench, options, *, in_menu)`. The commands `bench-show` and `bench-deploy` keep their option parsing, the session, and the bench pick, and then call these functions. The menu opens one session for the whole walk and calls the same functions. So the FC requests, the preview, and the typed confirmation are the same code for both paths.
- Alternative: the menu runs the CLI command again with arguments (`run(["bench-deploy", name])`). Rejected: a new session and a new team discovery for each action, and the Esc and Ctrl+C rules cannot change for the menu.

### D5. Menu loop and error handling
`menu.run` holds three levels: team, bench, action. Each level is a loop.

- **Errors:** each action call is wrapped. An `FcmError` is printed with `Output.error` (message, target, and hint), as the direct command prints it. Then the action menu opens again.
- **Ctrl+C in the watch:** with `in_menu=True`, `deploy_bench` raises an internal `WatchStopped` in place of `typer.Exit(130)`. The menu prints "The deploy continues on FC" and opens the action menu.
- **Cancelled confirmation:** this is a `UsageError`, so it follows the error path above, with no write.
- **Esc at the deploy app step:** with `in_menu=True`, `picker.GoBack` from the app step goes up to the menu, which shows the action menu. In the direct command, Esc keeps its current behavior (back to the bench step).
- **Ctrl+C at a menu prompt:** the picker already exits with code 2 on Ctrl+C. The menu changes this to exit 130 to match the spec. To do this, the menu catches the picker cancel signal at its own prompts only.

### D6. Target path on each prompt
`picker.choose` and `choose_many` get an optional `path` argument. When it is set, the prompt prints the path line (`work > ACME > ACME Prod (bench-1234)`) above the question, in a dim style. The path comes from the profile label, `team_label(team)`, and the bench title and name. The deploy walk passes the path when `in_menu=True`. The direct command does not pass it, because its target is in its preview.

### D7. No alias period
The two-word forms are removed in one step. The old-form error of D2 names the new command, so a broken script shows its fix. Reason: one user, no release.

## Risks / Trade-offs

- [Muscle memory and old notes use the two-word form] -> The D2 error names the new command, and it sends nothing to FC.
- [A long flat help list] -> Help panels group the 10 commands by noun.
- [The menu loop hides a failed action] -> Every error prints in full (message, target, hint) before the action menu opens again.
- [One session for a long menu walk] -> The API key does not expire during a session. A network error in an action is an error like any other, and the menu stays open.
- [Esc at the deploy app step differs between the menu and the direct command] -> The spec states both behaviors. In each case, Esc goes back one step of the walk that the user sees.

## Migration Plan

1. Rename the commands and add the D2 errors. Update the tests, the README, and the hints in one commit, so that no hint names an old form.
2. Add the menu.
3. Rollback: revert the commits. No stored data or config changes, so nothing else needs a rollback.
