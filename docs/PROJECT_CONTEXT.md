# Project context and operating decisions

This document transfers durable project context into the repository so a new coding agent can continue without relying on prior chat history. It is not a substitute for checking current upstream sources.

## Project purpose
A PS5-focused repository and payload catalog. The project collects configured source data and public GitHub repository/release metadata, normalizes it, validates generated feeds, and publishes JSON through GitHub Pages. It does not certify the safety, quality, or compatibility of upstream projects.

## Repository map
- `curated_repositories.json`: hand-curated repository additions and verified context.
- `curated_payloads.json`: hand-curated direct payload records/overrides.
- `convert.py`: main collection, merge, normalization, metadata, and output generation.
- `enrich_catalog.py`: payload description enrichment and changelog generation.
- `repositories.json`: generated repository index.
- `payloads_v2.json`: generated direct ELF payload feed.
- `icons.json`: generated icon map.
- `changelog.json`: generated change history (if present).
- `.github/workflows/update-catalog.yml`: scheduled/manual/push build, validation, and commit workflow.
- `README.md`: public overview and consumer-facing documentation.

## Durable editorial and data decisions
1. Canonical repository URL is the identity key for repository deduplication. Update existing entries instead of adding duplicates.
2. Keep projects separate when they have separate repositories and distinct roles, even if one depends on or bundles another.
3. ZIP, PKG/FFPKG, IMG, 7z, ISO, and release-page links are not direct ELF payloads. Keep such projects in the repository index when useful, with payload availability false unless a qualifying direct ELF asset is verified.
4. Never claim broad firmware/model/game compatibility from a single test. Preserve exact upstream prerequisites and conditional limitations.
5. Do not invent stars, downloads, checksums, version tags, dates, testing claims, or compatibility.
6. GitHub stars are not quality ratings; issue counts are not reviews.
7. PLDMGR display format: `⭐ stars · 📥 downloads · 🕒 short date | original description`. Do not append a separate Firmware field. Keep payload-specific original descriptions.
8. Compatibility notes belong in the original description only when sourced and useful.
9. Use direct HTTPS individual ELF URLs in the payload feed; a repository or release URL is not a payload download URL.
10. Preserve stable unique payload IDs, and do not collapse independently sourced assets merely because filenames or display names resemble one another.

## Previously handled projects and relationship notes
The following are historical verified notes from the previous maintenance work. Recheck current upstream README/releases before changing versions or compatibility statements.

### PC5
- Repository: https://github.com/bornaradusin/PC5
- PS5 homebrew launcher for managing the user's Windows games, installing from USB, presenting a game library with artwork, per-game settings, and DualSense support.
- Depends on `prospero-win` for running Windows software.
- README caveats included unsupported games requiring store launchers/online DRM, anti-cheat, or kernel drivers; no guarantee that a specific game works.
- Version previously checked: `v1.8.2` (27 October 2026).
- Distribution asset was `PPSA11018.zip`, not an individual ELF payload.
- Keep as a repository entry, not an ELF payload.

### prospero-win
- Repository: https://github.com/mpereiraesaa/prospero-win
- Experimental Windows runtime for PS5 homebrew, based on Wine; notes included 32-bit via a custom x86 translator and 64-bit native, DXVK/Vulkan and Mesa Zink, plus controller and keyboard/mouse support.
- Distribution was a PS5 application ZIP, not a standalone ELF payload.
- Compatibility varies; do not claim all Windows games work.
- Keep separate from PC5: it is the runtime/dependency, while PC5 is a launcher/library UI.

### PS5 Bazzite Deck
- Repository: https://github.com/VivaLaVent/ps5-bazzite-deck
- Bazzite-based PS5 Linux image booting into Steam Gaming Mode, with KDE desktop access. Runs from USB through rmux's PS5 Linux loader without modifying the PS5 system installation.
- README historically described original PS5, Slim, and Pro support with hardware-dependent HDMI and Wi-Fi/Bluetooth differences; firmware prerequisites depend on rmux loader. One README test reference was firmware 13.60, not universal compatibility.
- PS5 Pro support was noted from v1.8.4; HDMI features depend on hardware/TV; DualSense behavior changed in later versions.
- Distribution was split `.img.7z.00*` image archives, not an ELF payload.
- Keep as repository entry with payload availability false.

## Historical catalog addition state
The PS5 Bazzite Deck entry was added to `curated_repositories.json` in commit:
`3c837fe665956330e47b1626afea83f216265266`
The subsequent automation generated catalog files in commit:
`edfc3648fce6baab1119b2e2ce7b4086369a73d0`
A GitHub Actions run and GitHub Pages deployment were observed successful on 31 October 2026. Treat these as historical facts; verify current live state before relying on them.

## Related repositories and access boundaries
- `theeteempire/repos-database.json` is a separate repository database. Do not mirror curated records there automatically; inspect its schema and workflow first.
- `RDX-Sci01/PLDMGR_JSON` was used as a read-only reference. Do not write to it without explicit authorization.
- ChatGPT's GitHub connector credentials and permissions do not transfer to OpenCode. OpenCode must be authenticated independently.
