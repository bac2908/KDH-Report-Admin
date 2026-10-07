# Repository Guidelines

## Architecture & Ownership

KDH-Report-Admin owns data, provider integrations, sync, Dataset snapshots, Report Bundles, and admin workflow. KDH-Report-New owns customer-facing report presentation.

Data flow: `Provider -> Sync -> immutable Dataset -> Report Bundle -> KDH-Report-New`.

The current UI is single-client KinderHealth; retain `client_id` internally for architecture. Preserve the Vanilla JS / Flask architecture; do not introduce React or Vue.

## Data & Reporting

- Dataset snapshots and published/final report revisions are immutable.
- Report Builder and Preview operate only from immutable Dataset snapshots. Never call Google, Meta, TikTok, or YouTube provider APIs from these workflows.
- Use real backend data only; never fabricate business data to fill the UI.
- Never send provider credentials or OAuth tokens to KDH-Report-New. Keep secrets, `.env`, and `instance/` out of Git.
- Presentation-level section keys are `overview`, `seo`, `facebook_content`, `facebook_ads`, `tiktok`, `youtube`, and `gmb`. GA4, GSC, and Keywords are technical SEO data sources, not top-level report sections.

## Structure & Style

`kdh/` contains backend routes, services, providers, jobs, storage, and migrations. `templates/` and `static/` contain frontend code/assets; `tests/` holds suites; `docs/` holds architecture and API contracts.

Use four-space Python indentation and `snake_case`; JavaScript `camelCase` and semicolons. Match surrounding style; preserve Vietnamese UI text.

## Change Discipline

- Inspect the current working tree and existing implementation before editing. Never discard unrelated working-tree changes.
- Make minimal, targeted edits; do not rewrite large files wholesale.
- Reuse existing APIs, services, and routes before creating new ones. Never invent endpoints without confirming backend support.
- Preserve auth, Google OAuth, jobs, reports, datasets, and existing routes, including authorization and CSRF protections.
- Append numbered migrations in `kdh/migrations.py`; do not rewrite existing migrations.

## Development & Validation

Use Python 3.12+. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
npm.cmd ci --ignore-scripts
.\.venv\Scripts\python.exe run.py
```

`run.py` serves localhost:8090 with a worker.

After meaningful changes, run frontend tests, Python tests, JS syntax checks, and `git diff --check`:

```powershell
npm.cmd test
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Get-ChildItem static/*.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

Name Python tests `test_*.py`/`test_*`; add JSDOM cases in `tests/ui.test.js`. Mock providers. PostgreSQL tests require a disposable `TEST_DATABASE_URL`; otherwise they skip.

## Commits & Pull Requests

Do not commit or push unless explicitly requested. PRs should explain changes, validation, and migration impacts; link issues and include UI screenshots when relevant.
