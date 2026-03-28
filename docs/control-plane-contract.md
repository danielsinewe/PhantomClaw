# PhantomClaw Control Plane Contract

## Goal

The public `phantomclaw` repo should be able to produce portable run bundles that a private `phantomclaw-cli` uploads to the private PhantomClaw control plane.

## Roles

### Public `phantomclaw`

Responsible for:

- local execution
- fixture-driven testing
- run artifacts
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
- `phantomclaw workspace use <id-or-slug>`
- `phantomclaw sync run-bundle <path>`
- `phantomclaw dashboard open`

## Expected Hosted API Shape

Suggested endpoints:

- `POST /v1/device/start`
- `POST /v1/device/poll`
- `GET /v1/me`
- `GET /v1/workspaces`
- `POST /v1/run-bundles`
- `GET /v1/dashboard/link`

## Current OSS Export Path

The public repo now includes:

- bundle builder: [`phantomclaw_bundle.py`](../phantomclaw_bundle.py)
- export script: [`scripts/export_run_bundle.py`](../scripts/export_run_bundle.py)

This is the seam the private `phantomclaw-cli` should consume rather than reaching directly into runner internals.
