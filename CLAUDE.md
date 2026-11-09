# fc_manager

CLI/TUI to manage Frappe Cloud benches and deployments over several FC accounts.
Python. The development cycle is OpenSpec (spec-driven).

## OpenSpec

- The `openspec` CLI is not installed globally. Run it as `./bin/openspec` from the
  repo root. The wrapper pins version 1.16.1 and turns telemetry off.
- When an OpenSpec skill or `/opsx:*` command says `openspec ...`, run `./bin/openspec ...`.
- Living specs: `openspec/specs/`. Changes in progress: `openspec/changes/<id>/`.
  Finished changes: `openspec/changes/archive/`.
