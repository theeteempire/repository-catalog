# Agent instructions for Repository Catalog

These instructions apply to the entire repository. Follow them before making changes.

## Mission and source of truth
Maintain a reliable, evidence-based PS5 repository and payload catalog. The canonical project is this repository: https://github.com/theeteempire/repository-catalog.

Read the relevant source files before editing. Treat curated source files as human-maintained inputs and generated JSON as build outputs:
- `curated_repositories.json`: manually curated repository records.
- `curated_payloads.json`: manually curated payload records/overrides.
- `convert.py`: catalog generation and normalization.
- `enrich_catalog.py`: description enrichment and changelog generation.
- `repositories.json`, `payloads_v2.json`, `icons.json`, `changelog.json`: generated outputs; do not hand-edit unless the task explicitly requires a generated-data repair and the generator is also corrected.
- `README.md`: public project documentation.
- `.github/workflows/update-catalog.yml`: scheduled/manual/push automation and validation.

Related repositories:
- `https://github.com/theeteempire/repos-database.json`: separate repository database; inspect before changing it and do not assume every curated change must be copied there.
- `https://github.com/RDX-Sci01/PLDMGR_JSON`: reference/source repository only; read-only unless the user explicitly authorizes otherwise.

## Mandatory intake procedure for a repository URL
1. Confirm the canonical GitHub repository URL, owner, repository name, visibility, default branch, and current repository metadata.
2. Read the upstream README and inspect relevant documentation, releases, tags, and release assets. Prefer the latest stable release; distinguish prereleases.
3. Establish what the project actually is, what it depends on, distribution format, platform/model scope, firmware/loader prerequisites, and explicit limitations. Preserve conditional language.
4. Search both curated source and generated repository index for the canonical URL (normalize trailing slash and `.git`). Also check for aliases/forks where relevant. Never create a duplicate canonical repository entry.
5. If already curated, update that record rather than appending another. If it exists only in generated discovery, decide whether manual curation adds meaningful verified context.
6. Use evidence-backed fields only. Never invent stars, downloads, version, release date, firmware support, compatibility, tests, checksums, or direct asset URLs.
7. Keep related projects separate when they have distinct purposes, repositories, authors, or release artifacts. Describe dependencies accurately; do not merge them into one entry.
8. Add/update the source record in the correct curated file. Repository records belong in `curated_repositories.json`; only direct eligible payload assets belong in `curated_payloads.json`.
9. Do not classify ZIP, PKG/FFPKG, IMG, 7z, ISO, or a repository/release page as a direct ELF payload. A project may be a valid repository entry with `payload_available: false`.
10. Re-read changed files and validate JSON, canonical URL uniqueness, required fields, and consistency. Inspect the generated output after the workflow runs.

## Description and PLDMGR rules
- Write concise, factual descriptions that explain the project's function and important limitations.
- Keep compatibility caveats inside the original description only when supported by upstream evidence.
- Do not add a separate Firmware field to the PLDMGR display line.
- Expected PLDMGR display format: `⭐ stars · 📥 downloads · 🕒 short date | original description`.
- GitHub stars are popularity, not a five-star quality rating. Open issues are not reviews. Do not invent community sentiment.
- Downloads may be stated only when GitHub reports the count for the exact release asset.
- Missing metrics remain unknown/omitted according to the existing schema; never fabricate them.

## Validation and publishing
Before committing:
- Parse every edited JSON file with a real JSON parser.
- Check canonical repository URL duplicates and duplicate display names.
- Check payload IDs and normalized direct asset URLs for duplicates.
- Ensure payload URLs are HTTPS direct links to individual `.elf` files (not archives or release pages).
- Check icon references against `icons.json`.
- Run `python -m py_compile convert.py enrich_catalog.py` when Python files are changed.
- Run the workflow's validation logic or the full workflow locally where practical. Do not claim tests were run if they were not.
- Keep generated files consistent with their generator; normally let GitHub Actions regenerate them.
- Inspect GitHub Actions run status and logs, then inspect the resulting generated commit and published GitHub Pages feed. A source commit alone is not proof of publication.
- If a workflow is queued/running/failing or the live feed cannot be verified, say so explicitly. Never claim deployment succeeded without evidence.
- Do not trigger unnecessary duplicate builds. The update workflow runs on schedule, manually, and on configured source-file pushes.

## Git and permissions safety
- Work on the intended repository and default branch unless the user asks otherwise.
- Review `git status`, diffs, and current upstream state before committing or pushing.
- Never force-push, rewrite history, delete records, change workflow permissions, or alter branch protections without explicit user authorization.
- Do not expose, commit, print, or place GitHub tokens, private keys, passwords, cookies, or other secrets in files or logs.
- OpenCode's GitHub authentication is separate from ChatGPT's connector authorization. Ask the user to configure their own GitHub login/token in OpenCode; do not assume permissions have transferred.
- Prefer least-privilege GitHub access. Read-only is sufficient for research; write access is needed only to commit changes.
- Do not make changes to `RDX-Sci01/PLDMGR_JSON` without explicit authorization.

## Accuracy and communication
- State exactly what changed, in which files, and provide commit/run links when available.
- Distinguish source updates, generated output updates, and live deployment.
- Never say "done/published" based only on a local edit or source commit.
- If evidence is missing, state the limitation and ask for the smallest necessary clarification.
- Preserve user decisions and prior verified context documented in `docs/PROJECT_CONTEXT.md`, but re-check time-sensitive facts before relying on them.
