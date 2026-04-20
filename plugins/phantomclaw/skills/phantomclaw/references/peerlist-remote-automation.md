# Peerlist Remote Automation

## Classification

Remote Peerlist work usually falls into:

- Scroll posting.
- Scroll engagement.
- Launchpad support.
- Following coverage audits.
- Recurring automation.

For recurring remote automation, start with engagement rather than publishing. Publishing should be draft-only until preview and compliance behavior are verified.

## Compliance Gate

Hard bans:

- No unsolicited DMs asking for upvotes.
- No comments or replies asking for upvotes.
- No repeated launch-link reposting.
- No link-only Scroll posts.

Safe alternatives:

- Ask for product feedback or critique.
- Add build context, metrics, implementation details, or a specific question.
- Engage constructively with other creators before promoting your own launch.

## Safe Engagement Run

Default caps:

- 2-4 posts per run.
- Different creators where possible.
- At most one thoughtful comment.
- Random delays between actions.

Good comment criteria:

- Mentions a concrete detail from the post.
- Adds a useful suggestion, tradeoff, or question.
- Avoids generic praise.
- Avoids votes, launch pressure, or repetitive language.

Skip when:

- The post is too vague to comment on specifically.
- The action would look repetitive.
- The page is logged out or actor identity is unclear.
- Peerlist shows challenge or verification signals.

## Browser Runtime

Use the direct Railway runner for remote Peerlist runs:

```bash
NODE_PATH=/opt/openclaw/node_modules/.pnpm/playwright@1.58.2/node_modules:/opt/openclaw/node_modules/.pnpm/playwright-core@1.58.2/node_modules \
  PEERLIST_MAX_UPVOTES=1 \
  node /data/workspace/scripts/peerlist-browser-use-direct.mjs
```

Current provider order:

1. Browserbase CDP with `PEERLIST_COOKIES_JSON` from the logged-in local Chrome profile.
2. Browser Use CDP as fallback.

Why: Browser Use raw CDP repeatedly failed Peerlist navigation from Railway with `net::ERR_TUNNEL_CONNECTION_FAILED`, while Browserbase CDP with fresh Peerlist cookies verified Daniel and completed capped actions.

For healthchecks, run without engagement:

```bash
NODE_PATH=/opt/openclaw/node_modules/.pnpm/playwright@1.58.2/node_modules:/opt/openclaw/node_modules/.pnpm/playwright-core@1.58.2/node_modules \
  PEERLIST_HEALTHCHECK=1 \
  PEERLIST_MAX_UPVOTES=0 \
  node /data/workspace/scripts/peerlist-browser-use-direct.mjs
```

The healthcheck verifies provider connection, authenticated actor identity, page shape, visible upvote controls, artifact writes, and PhantomClaw/Neon sync. It never clicks.

To refresh the remote session from local Chrome:

```bash
node deployments/openclaw-railway/scripts/refresh-peerlist-session.mjs --healthcheck
```

The refresh helper syncs the local `danielsinewe.com` Chrome profile to Browser Use, exports fresh Peerlist cookies, updates Railway variables, and optionally runs a remote healthcheck.

Do not fall back to Railway-local headless Chrome for Peerlist engagement. If the provider is unavailable, logged out, challenged, or cannot confirm actor identity, fail closed and report the blocker.

The runner lives in this repo at `deployments/openclaw-railway/scripts/peerlist-browser-use-direct.mjs` and is copied to `/data/workspace/scripts/peerlist-browser-use-direct.mjs` on the Railway OpenClaw service.

The runner stores:

- normalized run bundle sync through PhantomClaw,
- JSONL run logs on the Railway volume,
- before/after screenshots under the Peerlist artifact directory,
- `browser_provider`, `provider_failures`, `healthcheck`, and `failure_category` metadata.

It also skips recently acted posts using the recent action keys in the JSONL log.

Legacy OpenClaw browser profile smoke checks can still inspect remote CDP:

```bash
openclaw browser --browser-profile browser-use open https://peerlist.io/scroll
openclaw browser --browser-profile browser-use snapshot --interactive
```

But do not use OpenClaw `/act` for this Peerlist cron yet:

- OpenClaw's loopback browser API can start Browser Use CDP, navigate, and snapshot reliably.
- OpenClaw `/act` ref actions against the Browser Use CDP session were observed to close or lose the target mid-run.
- Direct Playwright `connectOverCDP` is the verified execution path.

## Safe Posting Run

Default to draft-only. A publishable post needs:

- Approved context such as `#show` or `#ask`.
- Caption-first text.
- One concrete build detail.
- A feedback request, not an upvote request.
- A visible project preview/card if sharing a project link.

## Example Recurring Prompt

```text
Run a Peerlist Scroll engagement session through remote OpenClaw using browser profile `browser-use`.

Do not send DMs. Do not ask for upvotes. Do not publish posts. Engage with 2-4 high-signal posts from different creators. Use likes/upvotes where appropriate and at most one specific comment. Add randomized delays between actions. Skip low-signal, promotional, sensitive, unclear, or repetitive items. Stop if logged out, actor identity is unclear, or a challenge appears. Return links, actions, and skip reasons.
```
