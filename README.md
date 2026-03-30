# PhantomClaw

PhantomClaw is the open-source core for fail-closed browser automations, platform adapters, and normalized run analytics.

This repository is the public automation engine, not the full hosted product surface.

## Product Split

- `phantomclaw`:
  this repo, open source core runtime and public automation examples
- `phantomclaw.ai`:
  private website repo for marketing, onboarding, docs, and account entrypoints
- `phantomclaw-cli`:
  private authenticated CLI layer for cloud auth, managed database storage, and Looker Studio dashboard access

## Design Goals

- fail closed on auth drift, actor drift, challenge signals, or page-shape changes
- keep local runtime state and browser artifacts out of source control
- support both SQLite and Postgres-backed state
- normalize run KPIs across different automations and platforms

## Included Automations

- `linkedin.company_profile_engagement`: LinkedIn search engagement with guarded likes, reposts, comment likes, and company follows
- `linkedin.sales_community_engagement`: LinkedIn Sales Community engagement with bounded high-signal likes

## Quick Start

1. Create a virtual environment and install dependencies.
2. Copy [`.env.example`](./.env.example) to `.env` and fill in your own profile names and URLs.
3. Only add database credentials if you are intentionally self-hosting PhantomClaw state or analytics.
4. Run the test suite.
5. Dry-run a runner with fixtures before using a live browser session.

```bash
.venv/bin/python -m unittest
.venv/bin/python -m linkedin.company_profile_engagement.runner --dry-run --fixture tests/fixtures/normal_feed.html
.venv/bin/python scripts/export_run_bundle.py --automation-name linkedin-company-profile-engagement --report-path artifacts/linkedin-company-profile-engagement/<run-id>.json
.venv/bin/python scripts/export_run_bundle.py --print-schema
```

## Open Source Readiness

The repository includes:

- gitignored runtime outputs in [`.gitignore`](./.gitignore)
- contribution and support guidance in [`CONTRIBUTING.md`](./CONTRIBUTING.md), [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md), and [`SUPPORT.md`](./SUPPORT.md)
- secret-scanning and test automation in [`.github/workflows/ci.yml`](./.github/workflows/ci.yml)
- a gitleaks baseline config in [`.gitleaks.toml`](./.gitleaks.toml)
- launch framing notes in [`docs/open-source-launch.md`](./docs/open-source-launch.md)
- repo-boundary notes in [`docs/product-topology.md`](./docs/product-topology.md)
- control-plane handoff notes in [`docs/control-plane-contract.md`](./docs/control-plane-contract.md)

## Runtime Requirements

- Python 3.14+
- `browser-use` installed and available on `PATH`
- a dedicated Chrome profile already authenticated for the platform you want to automate

## Configuration

Shared:

- none required

Self-hosted only:

- `AUTOMATION_ANALYTICS_DATABASE_URL`

LinkedIn Company Profile Engagement:

- required: `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_SEARCH_URL`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_PROFILE`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ACTOR`
- optional: `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_SESSION`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_POST_CAP`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_REPOST_CAP`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_COMMENT_CAP`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_MAX_PASSES`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_FOLLOW_CAP`
- self-hosted only: `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_DATABASE_URL`, `LINKEDIN_COMPANY_PROFILE_ENGAGEMENT_ANALYTICS_DATABASE_URL`

LinkedIn Sales Community Engagement:

- required: `LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_PROFILE`
- optional: `LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_URL`, `LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_SESSION`, `LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_LIKE_CAP`, `LINKEDIN_SALES_COMMUNITY_ENGAGEMENT_ANALYTICS_DATABASE_URL`

## Artifacts And State

Local artifacts are written under `./artifacts/` and ignored by git.

LinkedIn Company Profile Engagement writes:

- `artifacts/linkedin-company-profile-engagement/` JSON reports and screenshots
- `artifacts/linkedin-company-profile-engagement/state.sqlite3` when Postgres is not configured

LinkedIn Sales Community Engagement writes:

- `artifacts/linkedin-sales-community-engagement/` JSON reports
- `artifacts/linkedin-sales-community-engagement/state.sqlite3` when Postgres is not configured

## Normalized Analytics

For self-hosted cross-automation dashboards, runners can write normalized facts into a shared Postgres sink via `AUTOMATION_ANALYTICS_DATABASE_URL` or an automation-specific `*_ANALYTICS_DATABASE_URL`.

This is not the PhantomClaw Cloud path. Managed PhantomClaw storage is expected to happen through authenticated `phantomclaw-cli` bundle sync, not by giving the public runner direct access to the hosted database.

The shared objects are:

- `automation_runs` as the durable fact table
- `automation_kpi_runs_v1` as the dashboard-friendly view
- `automation_action_events_v1` as the action drilldown view

The common fields are:

- identity: `automation_name`, `automation_label`, `platform`, `surface`, `run_id`, `profile_name`
- timing: `started_at`, `finished_at`, `duration_seconds`
- status: `status`, `stop_reason`
- KPIs: `items_scanned`, `items_considered`, `actions_total`, `likes_count`, `reposts_count`, `comments_liked_count`, `follows_count`, `companies_scanned`, `companies_followed`
- safeguards: `page_shape_ok`, `actor_verified`, `search_shape_ok`, `challenge_detected`
- extensibility: `metrics_json`, `action_events_json`, `report_json`
- action drilldown: `action_label`, `target_name`, `target_summary`, `target_url`, `target_locator`, `target_excerpt`, `post_url`, `company_url`, `selector`, `reason`, `message`

Legacy `agency_*` event names and count fields are normalized to `company_*` / `companies_*` when runs are stored or exported, so dashboard rows and bundles stay on the company terminology while older artifacts still load.

Platform-specific detail stays in `metrics_json`, while action-level drilldowns live in `automation_action_events_v1`, `action_events_json`, and `report_json.events`, so dashboards can stay stable while individual automations evolve. When `target_url` is unavailable for a historical LinkedIn post, `target_locator` still provides the post, comment, or company identifier so the row is not blank.

## Hosted Sync Seam

The public repo can export a portable `phantomclaw.run-bundle.v1` payload for the future private `phantomclaw-cli`.

That bundle is the contract between:

- open-source PhantomClaw core
- private authenticated CLI
- private PhantomClaw control plane and dashboard

For a new PhantomClaw Cloud user, the intended flow is:

1. run the automation locally
2. keep runtime state in local artifacts or your own self-hosted database
3. export a run bundle
4. authenticate with `phantomclaw-cli`
5. sync the bundle to PhantomClaw Cloud

The public CI also exports a bundle from a fixture report on every push so the contract stays live, not just documented.

## Repository Structure

The public structure is platform-first:

- `linkedin/company_profile_engagement/`
- `linkedin/sales_community_engagement/`

Within a platform, `surface` identifies the product area. Current LinkedIn surfaces are:

- `core`
- `sales-community`

This keeps `platform=linkedin` broad while still separating the main feed/product from products like Sales Community or Sales Navigator.
