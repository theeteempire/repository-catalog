# PS5 Repository List → PLDMGR catalog

This project downloads the upstream database and regenerates two JSON files every 6 hours.

Upstream source:
`https://raw.githubusercontent.com/nexgen999/PS5-Repository-List/main/json/repos-database.json`

## Important limitation

PLDMGR custom repositories are designed for **downloadable payload binaries**. Its schema requires each payload item to have `name`, `filename`, and a direct HTTP(S) `url`. The upstream file is a database of GitHub repositories, not a catalog of binary payload files.

This project therefore produces:

- `repositories.json`: the accurate index of all recognized GitHub repositories, including name, description, category, and repository URL.
- `payloads_v2.json`: a PLDMGR-shaped catalog intended to make all repository records visible. For repositories where no direct binary is known, `url` points to the GitHub repository page and `filename` is only a display identifier. Such entries are **not downloadable payloads**; clicking download/install may fail.

No checksums or direct download URLs are fabricated. The converter only uses repository URLs explicitly found in the source database. If the upstream database changes its schema, the workflow will fail rather than publish an empty catalog.

## Create the GitHub repository (beginner steps)

1. Go to https://github.com/new
2. Repository name: `ps5-repository-catalog`
3. Choose **Public**.
4. Check **Add a README file**, then click **Create repository**.
5. On the new repository page, click **Add file → Upload files**.
6. Upload all files from this project, including the hidden `.github/workflows/update-catalog.yml` file. If the browser upload makes hidden folders difficult, use the GitHub web editor to create `.github/workflows/update-catalog.yml` with the contents supplied in this project.
7. Click **Commit changes**.
8. Open **Actions**. If prompted, enable GitHub Actions.
9. Open **Update PS5 repository catalog** and click **Run workflow** once.
10. Wait for the workflow to finish. It commits `repositories.json` and `payloads_v2.json` to the `main` branch.

## Enable GitHub Pages

1. Open **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Choose branch `main` and folder `/ (root)`.
4. Click **Save**.

After Pages has deployed, your URLs will be:

- `https://YOUR-USERNAME.github.io/ps5-repository-catalog/payloads_v2.json`
- `https://YOUR-USERNAME.github.io/ps5-repository-catalog/repositories.json`

Replace `YOUR-USERNAME` with your GitHub username. Use the direct JSON URL (not the GitHub `blob` page) in PLDMGR.

## Automatic updates

The workflow runs every 6 hours and can also be started manually from **Actions → Update PS5 repository catalog → Run workflow**.

## Verify before using

Open the JSON URLs in a browser and check that they show raw JSON beginning with `{`. Check the workflow run logs if no generated files appear. The converter deliberately refuses to publish when it cannot identify repository URLs.

## Accuracy and safety

- Repository links and descriptions are taken from the source database.
- No checksums are generated.
- No payload binaries are downloaded or re-hosted.
- A GitHub repository page is not a payload binary. Do not treat display-only entries as installable files.
