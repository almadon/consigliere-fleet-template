# State

What is true right now, including what does not work. Delete this file if it stops being edited, so it does not become a misleading history. Last reviewed 2026-11-24.

## Works

- The layout, helper scripts and examples. `scripts/preflight.sh` and `scripts/routes_check.py` run clean on the unfilled template, apart from the expected placeholder and `.sops.yaml` warnings.

## Known gaps

- The `*_init.py` scripts were copied from a working fleet and given a required `--host`. They have not been run from the template. **VERIFY**
- Only some runbooks have been generalised for the template.
