# Security Policy

## Security posture (verified 2026-07-23)

- **Read-only by design:** the public API and NLP agent can only SELECT
  from three database views; the base table has row-level security
  enabled and grants revoked for API roles (`sql/create_tables.sql`).
- **No PII:** district-level financial aggregates only — no student or
  personnel data anywhere in the system.
- **Injection defenses:** parameterized queries throughout `src/api.py`;
  user-influenced column names come from a hardcoded allowlist; NLP agent
  is table-allowlisted and SELECT-only prompted.
- **Cost abuse:** `POST /query` is rate-limited per IP (see
  ENVIRONMENT.md); a CDN/WAF is recommended before large-scale promotion.
- **Secrets:** live only in the hosting provider's env vars; the repo,
  its history (secret-scanned — see AUDIT.md R2-3), and all docs contain
  none.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

**Do not open a public issue.** Instead, email security concerns to the repository maintainer.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix/Patch**: As soon as possible based on severity

## Supported Versions

| Version | Supported |
|---|---|
| Latest | Yes |
| Older | No |

## Security Best Practices

- Never commit API keys, tokens, or credentials
- Use environment variables for sensitive configuration
- Keep dependencies updated
- Report suspicious activity immediately
