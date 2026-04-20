# PhantomClaw Product Topology

## Repositories

`/Users/danielsinewe/Documents/GitHub/Automations`

- Public PhantomClaw automation core.
- Contains LinkedIn example runners today.
- Produces local artifacts and optional self-hosted analytics.
- Exports `phantomclaw.run-bundle.v1`.

`/Users/danielsinewe/Documents/GitHub/phantomclaw-cli`

- Private authenticated CLI.
- Owns login, token handling, workspace selection, bundle upload, and dashboard links.

`/Users/danielsinewe/Documents/GitHub/phantomclaw-ai`

- Private web/control-plane app.
- Owns account, dashboard, workspace UI, hosted storage, and bundle ingestion.

## Storage Boundary

The public runner should not require direct access to the hosted control-plane database. Direct Postgres writes from the OSS core are self-hosted mode. Hosted PhantomClaw Cloud should receive run data through authenticated `phantomclaw-cli` bundle sync.

## Current OSS Automations

- `linkedin.company_profile_engagement`
- `linkedin.sales_community_engagement`

Peerlist is currently documented as a remote OpenClaw/Codex Cron playbook, not yet a first-class OSS runner.

