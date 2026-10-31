# Repository intake and maintenance workflow

## A. Research an upstream project
1. Start from the exact repository URL supplied by the user.
2. Confirm owner/name, default branch, visibility, description, latest commit, and archived status.
3. Read README and relevant docs. Search the README for prerequisites, installation, supported hardware, firmware, limitations, and dependencies.
4. Inspect Releases, tags, and assets. Record latest stable release separately from prereleases.
5. Classify distribution accurately:
   - Individual `.elf`: potentially eligible for payload feed after URL and content checks.
   - ZIP/PKG/FFPKG/IMG/7z/ISO: package/archive/image, not an individual ELF.
   - Repository or release page: source reference, not a direct download asset.
6. Record source evidence for all claims. A single device/firmware test is not universal compatibility.

## B. Determine whether it already exists
1. Search `curated_repositories.json` for canonical URL.
2. Search `repositories.json` for canonical URL.
3. Normalize case, trailing slash, and optional `.git` suffix for comparison.
4. Search by owner/repository and project name to catch renamed or mirrored records.
5. If curated record exists, update it. If generated-only record exists, determine whether a curated override is needed. Never append a duplicate canonical URL.

## C. Choose the correct data source
- Repository metadata and project description: `curated_repositories.json`.
- Direct payload metadata/overrides: `curated_payloads.json`.
- Never place archive-only distribution in the direct ELF feed.
- Do not manually patch generated output as a substitute for fixing the source input or generator.

## D. Edit and validate
1. Make the smallest targeted change.
2. Preserve schema and existing formatting.
3. Parse changed JSON using Python's `json` module.
4. Check canonical URL uniqueness and display-name uniqueness.
5. Check payload IDs and normalized URL uniqueness.
6. Confirm every payload URL is HTTPS and ends in `.elf` (after removing query/fragment).
7. Confirm icon keys resolve in `icons.json`.
8. Run Python syntax checks if code changed.
9. Review the full diff; ensure no unrelated data churn or accidental secrets.

## E. Publish and verify
1. Commit/push to the intended branch only after review.
2. Inspect the matching GitHub Actions run. Check status, conclusion, and failed job logs if applicable.
3. Confirm generated commit updates expected files and metadata such as `generated_at`.
4. Confirm GitHub Pages deployment run succeeds.
5. Read the live published JSON feed and search for the canonical URL.
6. If any stage cannot be checked, report exactly which stage is unverified. A successful source commit does not prove generated output or website publication.

## Useful project URLs
- Repository: https://github.com/theeteempire/repository-catalog
- Actions: https://github.com/theeteempire/repository-catalog/actions
- Update workflow: https://github.com/theeteempire/repository-catalog/actions/workflows/update-catalog.yml
- GitHub Pages: https://theeteempire.github.io/repository-catalog/
- Repository feed: https://theeteempire.github.io/repository-catalog/repositories.json
- Payload feed: https://theeteempire.github.io/repository-catalog/payloads_v2.json
- Icon feed: https://theeteempire.github.io/repository-catalog/icons.json
