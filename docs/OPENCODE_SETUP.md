# OpenCode setup and handoff

## What is already in this repository
OpenCode automatically reads `AGENTS.md` when the repository is opened. The root `AGENTS.md` contains the durable project rules. Supporting context is in:
- `docs/PROJECT_CONTEXT.md`
- `docs/WORKFLOW.md`
- `docs/KNOWN_PROJECTS.md`
- `docs/PUBLISHING.md`

No ChatGPT conversation export is required for the documented workflow and decisions.

## Recommended setup
1. Install OpenCode using its official installation instructions: https://opencode.ai/docs/
2. Clone this repository:
   ```bash
   git clone https://github.com/theeteempire/repository-catalog.git
   cd repository-catalog
   ```
3. Open the folder in OpenCode:
   ```bash
   opencode
   ```
4. Authenticate GitHub independently. Use OpenCode's supported GitHub integration or the local GitHub CLI:
   ```bash
   gh auth login
   gh auth status
   ```
5. Confirm the account has repository read access. Grant write access only if you want OpenCode to commit/push changes.
6. Ask OpenCode to read `AGENTS.md` and all files under `docs/` before making its first change.

## Important security boundary
ChatGPT's connected GitHub authorization is not transferred to OpenCode. Do not copy credentials from ChatGPT or paste personal access tokens into prompts, source files, `.env` files committed to Git, or logs. Use the authentication flow supported by OpenCode/GitHub CLI and least-privilege permissions.

## First prompt to OpenCode
Use this prompt after opening the repository:

> Read AGENTS.md and every document in docs/. Then inspect the current repository state, git status, latest commits, curated source files, generated JSON, and recent GitHub Actions runs. Do not change anything yet. Summarize the architecture, current catalog state, outstanding workflow/deployment issues, and the exact safe procedure for adding or updating one PS5 repository. Confirm that PC5 and prospero-win must remain separate and that PS5 Bazzite Deck is an image project, not an ELF payload.

## Continuing work
For each new project, provide its canonical GitHub URL and ask OpenCode to follow the intake procedure in `AGENTS.md`. Review the proposed diff and validation results before allowing a commit or push.
