# PhantomClaw Open Source Launch Notes

## Positioning

PhantomClaw works best as a practical automation toolkit, not as a generic "AI agents do everything" project.

The core story is:

- fail-closed browser automations
- explicit state persistence and replayable artifacts
- normalized KPI reporting across multiple automations

## Recommended Launch Framing

- lead with reliability and safeguards, not growth hacking claims
- show one or two well-documented example automations
- make the analytics layer a secondary proof point, not the headline

## Suggested Monetization Direction

The cleanest commercial path is:

- open-source PhantomClaw core in this repo
- private `phantomclaw.ai` for the website and onboarding
- private `phantomclaw-cli` for auth, managed storage, and Looker Studio dashboard access

That keeps the automation engine public while reserving hosted identity and reporting as the paid layer.

## Launch Checklist

- scrub runtime artifacts before first push
- start with a minimal example `.env`
- publish clear fixture-based test instructions
- keep the first public README focused on one happy path
- add screenshots only after the public copy is stable
