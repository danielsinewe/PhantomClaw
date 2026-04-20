# PhantomClaw Plugin

This Codex plugin documents the current PhantomClaw/OpenClaw operating model:

- the public PhantomClaw automation core in this repository,
- the private `phantomclaw-cli` run-bundle sync boundary,
- the private `phantomclaw.ai` control plane,
- the Railway-hosted OpenClaw gateway,
- safe remote automation patterns for Peerlist.

## Contents

- `.codex-plugin/plugin.json`: plugin manifest.
- `skills/phantomclaw/SKILL.md`: primary Codex skill.
- `skills/phantomclaw/references/remote-openclaw-railway.md`: Railway/OpenClaw remote gateway notes.
- `skills/phantomclaw/references/peerlist-remote-automation.md`: Peerlist remote automation compliance and run patterns.
- `skills/phantomclaw/references/product-topology.md`: repo and product boundary notes.

## Current Remote Gateway

The observed Railway OpenClaw gateway is:

```text
wss://openclaw-production-22d3d.up.railway.app/openclaw/
```

The gateway token is intentionally not documented. Treat it as a secret stored in Codex Desktop or Railway variables.

## Recommended First Remote Automation

Start with capped Peerlist Scroll engagement, not publishing:

- 2-4 posts per run,
- different creators,
- at most one thoughtful comment,
- random delays,
- strict skip behavior,
- no DMs,
- no upvote asks,
- no repeated launch-link spam.

