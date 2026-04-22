# PhantomClaw Product Blueprint

## Positioning

PhantomClaw is a cloud automation platform for AI-agent-native growth and operations workflows.

It should feel familiar to users who understand automation libraries like Phantombuster, but the product direction is broader:

- cloud-first execution,
- AI-agent-driven decision making,
- customizable workflow parameters,
- reusable automation bundles,
- open-source-like bundle distribution,
- private hosted control plane,
- strong run evidence, metrics, and safety gates.

The platform itself does not have to be open source. The automation bundles, skills, schemas, examples, and recipes should feel open-source-like: inspectable, forkable, versioned, testable, and portable.

## Core Product Thesis

Traditional automation tools mostly run deterministic scripts against one platform surface. PhantomClaw should run configurable AI-assisted workflows that combine:

- deterministic guards,
- platform-specific adapters,
- agent reasoning where it adds value,
- browser or HTTP execution backends,
- measurable business outcomes,
- daily north-star metrics,
- audit trails for every mutation.

The product is not just "click this button every day." It is "run this outcome-oriented workflow safely, explain what happened, and show whether the north-star metric improved."

## Product Surfaces

### PhantomClaw Cloud

Private hosted control plane.

Responsibilities:

- account and workspace management,
- secrets and connected accounts,
- automation bundle catalog,
- schedule and run configuration,
- run history and action-event drilldown,
- daily north-star metrics,
- billing, quotas, and team permissions.

### PhantomClaw Runtime

Cloud execution layer, currently OpenClaw on Railway.

Responsibilities:

- run scheduled workflows,
- execute browser/API/HTTP adapters,
- enforce caps and safety gates,
- produce `phantomclaw.run-bundle.v1`,
- sync results to hosted storage.

Runtime providers should be swappable:

- OpenClaw-managed browser,
- Browser Use Cloud/CDP,
- Browserbase/CDP,
- direct authenticated platform HTTP APIs,
- future self-hosted workers.

### PhantomClaw Bundles

Reusable automation packages.

Bundles should be open-source-like even when the hosted platform is private. A user should be able to inspect:

- what the workflow does,
- what permissions it needs,
- what parameters it accepts,
- what safety gates it enforces,
- what metrics it emits,
- what actions it can mutate,
- what tests and fixtures prove the behavior.

## Bundle Standard

Every automation bundle should include:

- `bundle.json`: metadata, version, platform, category, permissions, supported runtimes.
- `SKILL.md`: agent-facing operating instructions.
- `README.md`: human-facing setup, limits, examples, and compliance notes.
- `schema.json`: parameters, report, action events, and metrics.
- `runner`: deterministic or agent-assisted implementation.
- `fixtures/`: representative pages/API payloads.
- `tests/`: parser, filter, cap, and safety tests.
- `examples/`: dry-run and live-run commands.
- `CHANGELOG.md`: versioned behavior changes.

Minimum bundle metadata:

```json
{
  "name": "peerlist-follow-workflow",
  "label": "Peerlist Follow/Unfollow",
  "version": "0.1.0",
  "platform": "peerlist",
  "surface": "network",
  "category": "audience-growth",
  "kind": "workflow",
  "north_star_metric": "peerlist_profile_followers",
  "actions": [
    "peerlist_profile_followed",
    "peerlist_profile_unfollowed"
  ],
  "runtimes": [
    "openclaw-railway",
    "browser-use-cloud",
    "browserbase-cdp",
    "self-hosted"
  ],
  "default_mode": "dry-run",
  "risk_level": "medium"
}
```

## Runtime Contract

Each run must produce a `phantomclaw.run-bundle.v1` payload.

Required sections:

- `source`: runtime and provider details.
- `automation`: durable bundle identity and parameters.
- `run`: status, timestamps, target profile, action events.
- `metrics`: normalized counts and platform-specific metrics.
- `report`: raw runner output, blockers, skipped rows, and diagnostics.

Statuses:

- `ok`: at least one verified intended action happened.
- `no_action`: actor verified, but caps/filtering produced no mutation.
- `blocked`: a safety gate stopped the run before mutation.
- `error`: unexpected runner failure.

No workflow should count an action unless post-action verification confirms it.

## Safety Model

The product should bias toward safe, explainable automation instead of maximum volume.

Required safety primitives:

- dry-run default,
- explicit live flag,
- per-run caps,
- daily caps enforced from durable action-event storage,
- cooldowns,
- allowlists and blocklists,
- peer/mutual-relationship preservation,
- authenticated actor verification,
- challenge/CAPTCHA detection,
- fail-closed behavior,
- no hidden retries that multiply mutations,
- per-action verification,
- full action-event audit trail.

For social platforms, avoid workflows that send unsolicited DMs, ask for upvotes, publish spam, or hide automated behavior behind misleading interaction patterns.

## Metrics Model

PhantomClaw should separate run facts from outcome metrics.

Run facts answer:

- What did the automation do?
- Which targets were scanned?
- Which targets were skipped and why?
- Which actions were verified?
- Which blocker stopped the run?

Timestamped north-star metrics answer:

- Is the user getting the outcome they wanted?
- Is the trend improving across runs, days, and weeks?

Store:

- run facts in `automation_runs`,
- mutation audit rows in `automation_action_events_v1`,
- append-only absolute outcome snapshots in `automation_daily_metrics` and `automation_daily_metrics_v1`.

Use `captured_at_ts` for timestamped north-star charts. Use daily grouping only when the chart should show one value per day. Use per-run deltas only for attribution and debugging.

## First Bundle: Peerlist Follow/Unfollow

The first canonical PhantomClaw bundle is `peerlist-follow-workflow`.

Goal:

- increase the authenticated user's own Peerlist follower count.

North-star metric:

```text
peerlist_profile_followers
```

Initial actions:

- follow selected Peerlist profiles,
- later unfollow profiles after a configured age,
- never unfollow mutual peers when peer preservation is enabled.

Default parameters:

```json
{
  "type": "follow",
  "follows_per_day": 3,
  "max_follows_per_run": 1,
  "unfollows_per_day": 10,
  "max_unfollows_per_run": 1,
  "unfollow_after_days": 14,
  "do_not_unfollow_peers": true,
  "active_window_start": "09:00",
  "active_window_end": "21:00",
  "min_delay_seconds": 45,
  "max_delay_seconds": 180,
  "candidate_pool_limit": 50,
  "require_verified_profile": false,
  "skip_existing_following": true,
  "skip_existing_followers": false,
  "skip_peers": true,
  "profile_blacklist": [],
  "profile_whitelist": []
}
```

Scheduling should mirror the Phantombuster mental model, but keep launch frequency separate from action volume:

- launch mode: once, repeatedly, after another workflow, advanced
- frequency presets: every other day, daily, twice daily, 3/4/6/8 times daily, every other hour, hourly, 2/3/4 times hourly
- working-hours variants: 09:00-17:00 with an option to exclude weekends
- action caps: `follows_per_day`, `max_follows_per_run`, `unfollows_per_day`, `max_unfollows_per_run`
- lifecycle controls: `unfollow_after_days`, `do_not_unfollow_peers`, blacklist, whitelist

Current verified runtime:

```text
OpenClaw on Railway
  -> OpenClaw cron
  -> /usr/local/bin/run-peerlist-follow-workflow.sh
  -> authenticated Peerlist HTTP backend
  -> phantomclaw.run-bundle.v1
  -> Neon/Postgres analytics sync
```

Current production state:

- live conservative cron is enabled,
- max 3 verified follows per Europe/Berlin day,
- max 1 verified follow per run,
- daily cap is enforced from Neon action events,
- follower snapshots are stored separately as append-only timestamped north-star metric rows.

## Bundle Roadmap

After Peerlist follow/unfollow, likely bundles:

- Peerlist Scroll engagement.
- Peerlist Launchpad support and discovery.
- LinkedIn company profile engagement.
- LinkedIn Sales Navigator list enrichment.
- GitHub repository star/follow discovery workflows.
- X/Twitter profile engagement, only if compliance and account-safety rules are strict enough.
- Product Hunt launch support.
- CRM enrichment workflows for HubSpot.
- SEO/AI visibility monitoring workflows.

Each new bundle should ship with:

- a north-star metric,
- a dry-run mode,
- cap enforcement,
- verified action events,
- daily metric snapshots,
- fixtures and tests,
- clear compliance notes.

## Product Differentiators

PhantomClaw should differentiate on:

- AI-agent-native workflows, not only static scripts.
- Outcome metrics, not only action logs.
- Bundle transparency and portability.
- Runtime flexibility.
- Strong safety gates.
- Cloud scheduling with auditable run evidence.
- Customizable parameters for non-technical users and editable bundle code/instructions for technical users.

The product promise should be:

```text
Install a proven automation bundle, customize the strategy, run it safely in the cloud, and measure whether it improves the metric you care about.
```
