# PhantomClaw Plugin

This Codex plugin documents the current PhantomClaw/OpenClaw operating model:

- the public PhantomClaw automation core in this repository,
- the private `phantomclaw-cli` run-bundle sync boundary,
- the private `phantomclaw.ai` control plane,
- the Railway-hosted OpenClaw gateway,
- safe remote automation patterns for Peerlist.
- the product direction: a cloud-based, AI-agent-focused automation platform with reusable open-source-like automation bundles.

## Contents

- `.codex-plugin/plugin.json`: plugin manifest.
- `skills/phantomclaw/SKILL.md`: primary Codex skill.
- `skills/phantomclaw/references/remote-openclaw-railway.md`: Railway/OpenClaw remote gateway notes.
- `skills/phantomclaw/references/peerlist-remote-automation.md`: Peerlist remote automation compliance and run patterns.
- `skills/phantomclaw/references/product-topology.md`: repo and product boundary notes.
- `skills/phantomclaw/references/product-blueprint.md`: product positioning, bundle model, runtime contract, and the first Peerlist follow/unfollow bundle.

## Current Remote Gateway

The observed Railway OpenClaw gateway is:

```text
wss://openclaw-production-22d3d.up.railway.app/openclaw/
```

The gateway token is intentionally not documented. Treat it as a secret stored in Codex Desktop or Railway variables.

## Product Direction

PhantomClaw should be similar in spirit to an automation-library product, but more cloud-native, AI-agent-focused, customizable, and outcome-measured.

The hosted platform remains private. The automation bundles should feel open-source-like: inspectable, forkable, versioned, testable, and portable.

The first canonical bundle is `peerlist-follow-workflow`, with `peerlist_profile_followers` as the north-star metric.

## Recommended First Remote Automation

Start with capped Peerlist follow/unfollow, not publishing:

- max 3 verified follows per day,
- max 1 verified follow per run,
- never target mutual peers,
- verify every follow after mutation,
- store every verified action event,
- store daily own-follower snapshots,
- enforce daily caps from durable storage,
- random delays,
- strict skip behavior,
- no DMs,
- no upvote asks,
- no repeated launch-link spam.
