# PhantomClaw Control Plane Contract

## Goal

The public `phantomclaw` repo should be able to produce portable run bundles that a private `phantomclaw-cli` uploads to the private PhantomClaw control plane.

The public repo should not require direct access to the managed PhantomClaw Cloud database. Direct Postgres writes in the OSS core are a self-hosted mode, not the hosted product contract.

## Roles

### Public `phantomclaw`

Responsible for:

- local execution
- fixture-driven testing
- run artifacts
- local SQLite state by default
- optional self-hosted Postgres state and analytics
- normalized metrics
- building run bundles for upload

### Private `phantomclaw-cli`

Responsible for:

- login and token management
- workspace selection
- uploading run bundles
- opening or linking the hosted dashboard

### Private `phantomclaw.ai`

Responsible for:

- website
- account management
- billing
- dashboard and workspace UI

## Run Bundle Format

The OSS core exports `phantomclaw.run-bundle.v1`.

Top-level sections:

- `schema_version`
- `generated_at`
- `source`
- `automation`
- `run`
- `metrics`
- `report`

The bundle intentionally includes both normalized metrics and the raw report so the private product can store a durable source payload while also powering dashboard summaries.

## Expected Private CLI Commands

- `phantomclaw login`
- `phantomclaw whoami`
- `phantomclaw workspace list`
- `phantomclaw workspace create <name> [--slug <slug>]`
- `phantomclaw workspace use <id-or-slug>`
- `phantomclaw sync run-bundle <path>`
- `phantomclaw dashboard open`

## Expected Hosted API Shape

Suggested endpoints:

- `POST /v1/device/start`
- `POST /v1/device/poll`
- `GET /v1/me`
- `GET /v1/workspaces`
- `POST /v1/workspaces`
- `POST /v1/run-bundles`
- `GET /v1/dashboard/link`

## Current OSS Export Path

The public repo now includes:

- bundle builder: [`phantomclaw_bundle.py`](../phantomclaw_bundle.py)
- export script: [`scripts/export_run_bundle.py`](../scripts/export_run_bundle.py)
- schema document: [`schemas/phantomclaw.run-bundle.v1.schema.json`](../schemas/phantomclaw.run-bundle.v1.schema.json)

The schema can be inspected directly without a run artifact:

```bash
.venv/bin/python scripts/export_run_bundle.py --print-schema
```

This is the seam the private `phantomclaw-cli` should consume rather than reaching directly into runner internals.

The private CLI CI should check out the public repo, export a real fixture bundle from this OSS codebase, and run its own sync smoke against a mock control plane. That keeps the OSS export path and private CLI parser in lockstep.

## Product Boundary

For PhantomClaw Cloud, the intended storage flow is:

1. public runner executes locally
2. local artifact and state are produced
3. authenticated `phantomclaw-cli` uploads a run bundle
4. private control plane stores and serves managed dashboard data

If a user sets `AUTOMATION_ANALYTICS_DATABASE_URL` or an automation-specific `*_DATABASE_URL`, that should be understood as self-hosting, not as the default hosted-user experience.
