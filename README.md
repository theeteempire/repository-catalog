# PS5 Repository Catalog

Automatically generated catalog for PS5 projects and PLDMGR-compatible payload downloads.

## Live JSON feeds

- **PLDMGR payload feed:** `https://theeteempire.github.io/ps5-repository-catalog/payloads_v2.json`
- **Full repository index:** `https://theeteempire.github.io/ps5-repository-catalog/repositories.json`
- **Icon database:** `https://theeteempire.github.io/ps5-repository-catalog/icons.json`

Use the `payloads_v2.json` URL in PLDMGR. The other files provide the full project index and icon data.

## What the generator does

Every six hours, GitHub Actions:

1. Downloads the upstream PS5 repository database.
2. Retains the maintained itsPLK payload catalog's curated metadata, direct links, versions, checksums, and icon keys.
3. Checks repositories without a curated payload entry against the GitHub Releases API.
4. Adds extra release assets only when they are direct HTTPS `.elf` downloads. Repository pages and release landing pages are never presented as installable payloads.
5. Builds a standalone `icons.json`, preserving the original itsPLK icon data and adding hashed GitHub avatar images as a fallback for newly discovered release entries when available.
6. Validates the generated JSON and verifies every PLDMGR `url` points to an HTTPS `.elf` asset before committing the results.

## Payload metadata

Entries preserve the fields used by the itsPLK feed where the upstream data provides them, including:

- `name`, `filename`, `url`
- `source`, `source_direct`
- `description`, `category`
- `version`, `last_update`
- `checksum` only when a trusted upstream digest is supplied
- `icon_key` only when an icon exists in the icon database

The generator does **not** invent release tags, hashes, or binary URLs. An upstream GitHub release may package a payload inside a ZIP rather than as an individual ELF asset; such archives are not automatically treated as directly installable ELF payloads. They remain discoverable in the repository index.

## JSON files

- `payloads_v2.json`: only payload records with a direct HTTPS URL ending in `.elf`.
- `repositories.json`: the complete recognized repository index, enriched with payload metadata where a reliable match exists.
- `icons.json`: icon map keyed by SHA-256 hashes. Existing itsPLK icons are retained; repository avatars are only a fallback for entries without an existing icon.

The payload feed includes `icons_url: "icons.json"`. GitHub Pages serves these files from the same directory.

## Automatic updates

The workflow runs every six hours and can also be started manually:

**GitHub → Actions → Update PS5 repository catalog → Run workflow**

It uses the workflow's built-in `GITHUB_TOKEN` for release API requests and needs no personal access token. The workflow validates output before committing it.

## Sources

- Repository database: [nexgen999/PS5-Repository-List](https://github.com/nexgen999/PS5-Repository-List)
- Curated payload feed and original icon metadata: [itsPLK/ps5-payloads-mirror](https://github.com/itsPLK/ps5-payloads-mirror)

## Accuracy notes

- A direct download URL is not a guarantee that a payload supports every PS5 firmware version or configuration. Check the project's release notes and requirements.
- Checksums are included only when supplied by a trusted source. Missing checksums are left absent.
- Icons are preserved from the upstream icon map where available; GitHub avatars are used as a fallback, not misrepresented as official project logos.
- This project indexes public release assets; it does not modify payload binaries.
