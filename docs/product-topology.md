# PhantomClaw Product Topology

## Public Repo

`phantomclaw` is the open-source core.

It should contain:

- fail-closed runner logic
- platform and surface abstractions
- local and self-hosted state handling
- normalized analytics schema
- public examples, fixtures, and docs

It should not contain:

- hosted auth implementation
- production customer database credentials
- private billing or account logic
- private website content or conversion funnels

## Private Repos

### `phantomclaw.ai`

Private website repo for:

- marketing site
- docs landing pages
- signup and login entrypoints
- pricing and onboarding flows

### `phantomclaw-cli`

Private authenticated CLI repo for:

- user auth
- linking a user or workspace to managed storage
- writing run data into the managed database
- exposing access to the Looker Studio dashboard
- eventually syncing local runner state to hosted services

## Recommended Boundary

Use the open-source repo for runtime logic and public adapters. Keep cloud identity, billing, and hosted analytics access in private repos.

That gives PhantomClaw an open distribution engine while preserving the managed product moat around auth, storage, and hosted reporting.

