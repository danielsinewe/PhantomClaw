# Security Policy

## Reporting

If you discover a security issue, do not open a public issue with exploit details or credentials. Report it privately to the maintainers first.

## Repository Hygiene

- Never commit live credentials, browser profile data, or local session artifacts.
- Use [`.env.example`](./.env.example) for configuration shape only.
- Runtime output belongs under ignored local paths such as `artifacts/` and `.tmp/`.
