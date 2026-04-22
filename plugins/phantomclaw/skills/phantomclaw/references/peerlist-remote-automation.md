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
/usr/local/bin/run-peerlist-follow-workflow.sh
```

Current provider order:

1. Peerlist authenticated HTTP backend with `PEERLIST_COOKIES_JSON`.
2. Browser Use CLI, Browser Use CDP/SDK, Browserbase CDP, or OpenClaw browser actions as fallback/debug paths.

Why: the Peerlist HTTP backend verified Daniel and synced Neon from Railway/OpenClaw on 2026-04-21 without depending on Railway headless Chrome or hosted browser-provider availability. Browser Use and Browserbase paths hit provider-side tunnel, billing, credit, or session constraints during the latest verification.

For a dry-run healthcheck/discovery pass, leave live mode off:

```bash
/usr/local/bin/run-peerlist-follow-workflow.sh
```

The dry run verifies provider connection, authenticated actor identity, visible follow candidates, artifact writes, and Neon sync. It never clicks.

For a capped live proof:

```bash
PEERLIST_FOLLOW_LIVE=1 PEERLIST_FOLLOWS_PER_DAY=1 \
  /usr/local/bin/run-peerlist-follow-workflow.sh
```

To refresh the remote session from local Chrome:

```bash
node deployments/openclaw-railway/scripts/refresh-peerlist-session.mjs --healthcheck
```

The refresh helper syncs the local `danielsinewe.com` Chrome profile to Browser Use, exports fresh Peerlist cookies, updates Railway variables, and optionally runs a remote healthcheck.

Do not fall back to Railway-local headless Chrome for Peerlist engagement. If the provider is unavailable, logged out, challenged, or cannot confirm actor identity, fail closed and report the blocker.

The default follow workflow runner lives in this repo at `scripts/run_peerlist_follow_http.py`, is staged into the Railway image at `/opt/phantomclaw`, and is wrapped by `/usr/local/bin/run-peerlist-follow-workflow.sh`.

The runner stores:

- normalized run bundle sync through PhantomClaw,
- JSONL run logs on the Railway volume,
- `browser_provider` metadata.

It also skips recently acted posts using the recent action keys in the JSONL log.

Legacy OpenClaw browser profile smoke checks can still inspect remote CDP:

```bash
openclaw browser --browser-profile browser-use open https://peerlist.io/scroll
openclaw browser --browser-profile browser-use snapshot --interactive
```

But do not use OpenClaw `/act` as the primary Peerlist cron path yet:

- Hosted browser paths were unreliable during the latest Railway checks.
- The HTTP backend is the verified scheduled execution path.
- Browser sessions remain useful for visual debugging, screenshots, and login/session repair.

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
