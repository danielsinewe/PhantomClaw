# Contributing

## Development

1. Create a virtual environment and install dependencies from [`pyproject.toml`](./pyproject.toml).
2. Copy [`.env.example`](./.env.example) to `.env` and fill in your own values.
3. Run the test suite before opening a pull request:

```bash
.venv/bin/python -m unittest
```

## Scope

- Keep automations fail-closed. If page shape, actor identity, or auth state drifts, stop instead of guessing.
- Do not hardcode local file paths, profile names, or production credentials.
- Prefer additive, well-tested changes over broad rewrites.

## Pull Requests

- Describe the automation or platform affected.
- Include any schema or dashboard changes.
- Add or update tests for behavior changes.
