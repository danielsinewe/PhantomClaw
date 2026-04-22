# PhantomClaw Product Topology

## Product Direction

PhantomClaw should be a cloud-based, AI-agent-focused automation platform with reusable automation bundles.

The platform itself can remain private. The automation bundles should feel open-source-like:

- inspectable,
- forkable,
- versioned,
- testable,
- portable across runtimes,
- documented with clear parameters, permissions, safety gates, and metrics.

The first canonical bundle is `peerlist-follow-workflow`, a Peerlist follow/unfollow workflow whose north-star metric is the authenticated user's own follower count: `peerlist_profile_followers`.

See `product-blueprint.md` for the full positioning and bundle standard.

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

Peerlist follow/unfollow is now the first canonical workflow bundle direction:

- `automation_name`: `peerlist-follow-workflow`
- `platform`: `peerlist`
- `surface`: `network`
- `north_star_metric`: `peerlist_profile_followers`
- verified runtime: OpenClaw on Railway
- verified backend: authenticated Peerlist HTTP APIs
- storage: `phantomclaw.run-bundle.v1`, action events, and daily north-star metrics
