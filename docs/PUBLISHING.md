# Build, validation, and publication

## Automation
The workflow is `.github/workflows/update-catalog.yml`. It supports:
- Scheduled runs every six hours.
- Manual `workflow_dispatch`.
- Push-triggered runs for configured source files on `main`.

The workflow checks out `main`, installs Python and Pillow, compiles the Python scripts, runs `convert.py` and `enrich_catalog.py`, validates generated JSON/URLs/icons/IDs, and commits generated catalog files when they change. GitHub Pages deployment is a separate workflow/run.

## Generated files
- `repositories.json`: repository index.
- `payloads_v2.json`: direct ELF payload feed.
- `icons.json`: icon data.
- `changelog.json`: generated change record when produced by the enrichment step.

Do not treat a successful source commit as proof that generated files or Pages are current.

## Verification checklist
1. Locate the Actions run for the source commit.
2. Confirm the catalog update workflow conclusion is `success`.
3. If failed, inspect the failed job and relevant log section; fix the underlying source or generator problem rather than editing outputs blindly.
4. Confirm the generated-data commit contains the expected files and updated `generated_at`.
5. Confirm the Pages build/deployment run is `success`.
6. Fetch the live JSON feed and verify the exact canonical repository URL and expected fields.
7. Report the source commit, generated commit, workflow run, deployment run, and live-feed result separately.

## Historical verified publication
On 31 October 2026, the update workflow run `41206112359` and Pages deployment run `41206639001` were observed successful after the PS5 Bazzite Deck catalog update. Generated commit: `edfc3648fce6baab1119b2e2ce7b4086369a73d0`. These are historical records, not a guarantee of current state.
