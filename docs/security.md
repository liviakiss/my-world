# My World — Security

Living document: what the app protects, how, and why. Updated as features are built.

## Attack surface (so far)

| Surface | Main threats |
| --- | --- |
| `POST /auth/signup` | account enumeration, timing attacks, oversized input, duplicate accounts via race condition |
| `POST /auth/login` | brute force, credential stuffing, account enumeration, timing attacks |
| `POST /auth/refresh` | stolen refresh token, token replay |
| Session cookies | XSS token theft, CSRF |
| Database | credential leak, SQL injection, data leak through errors |
| Request validation | sensitive input echoed back in error responses |

## Controls in place

### Passwords
- Argon2id via pwdlib (memory-hard, salted per password).
- Length 12–128. The upper limit stops oversized inputs from tying up the server with slow hashing (DoS).
- Plain passwords are never stored or logged.

### Account enumeration
- Signup returns the same `202` message whether the email is new or taken.
- Login returns the same `401 Invalid email or password.` for unknown email, wrong password and locked account.
- Timing is equalized: signup always hashes; login runs a dummy Argon2 verification when there is no real hash to check.

### Brute force
- 5 failed logins → account locked for 15 minutes; during lockout even the correct password is rejected.
- Every failure, lockout and success is written to `security_events`.
- Per-IP rate limits (sliding window): signup 5/min, login 10/min, refresh 30/min → `429` with `Retry-After`.
- Account lockout stops guessing one account; rate limiting stops one source guessing many accounts (credential stuffing).
- Trade-off: an attacker can deliberately lock a victim's account for 15 minutes. Accepted for now; the lock is short and every lock is logged.
- Limits are kept in memory per server process: fine for one instance, would move to Redis when scaling out.

### Sessions
- Short-lived access token (JWT, HS256, 15 min) and long-lived refresh token (random 256-bit, 14 days).
- Both in `httpOnly` cookies (unreadable from JavaScript → XSS cannot steal them), `SameSite=Lax` (blocks cross-site POSTs → CSRF), `Secure` in production.
- Refresh cookie is scoped to `/auth`, so it is not sent with ordinary API requests.
- Refresh tokens are stored as SHA-256 hashes; a database leak does not expose usable tokens.
- Rotation: every refresh revokes the old token and issues a new one in the same family.
- Reuse detection: presenting an already-used refresh token revokes the whole family and logs `refresh_token_reused`.
- JWTs are decoded with a fixed algorithm list (prevents `alg: none` / algorithm confusion) and required claims.

### Secrets and configuration
- All secrets in environment variables, typed as `SecretStr` (masked in logs and errors).
- App refuses to start if a secret is missing or shorter than 32 characters (fail fast).
- `alembic.ini` contains no credentials.
- Database connection requires TLS (`sslmode=require`) and channel binding.

### Data protection
- UUID primary keys (no ID enumeration).
- IP addresses stored only as HMAC-SHA256 with a server secret (GDPR; a plain hash of an IPv4 address could be brute-forced).
- User-Agent trimmed to 300 characters before storage.
- Account deletion cascades to entries, custom works, analytics events and refresh tokens; security events are kept but unlinked (`SET NULL`).
- Database CHECK constraints enforce valid progress, ratings, note length and date order.

### HTTP hardening
- Security headers on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- API responses: `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` and `Cache-Control: no-store` (personal data is never cached by browsers or proxies).
- HSTS (2 years) whenever cookies are `Secure`, i.e. in production.
- CORS allowlist: only configured frontend origins may make credentialed requests.
- Interactive API docs (`/docs`, `/openapi.json`) are disabled in production.

### Error handling
- Validation errors return field + message only, never the submitted value.
- Database errors return a generic `503`; details stay server-side.
- External API text is rendered as plain text only (XSS).

## Verification
- Automated tests (`backend/tests`) prove each control: identical responses for taken/unknown emails, no password echo, lockout, cookie flags, token rotation, reuse detection, forged / expired / `alg: none` JWTs rejected, rate limits, headers and CORS.
- Tests run against a separate database; the suite refuses to start if it points at the development database.
- CI on every push: tests against a fresh Postgres, gitleaks (secret scanning, full history), Bandit (static analysis), pip-audit (known-vulnerable dependencies). Dependabot keeps dependencies and actions updated.

## Known gaps / planned
- Email verification and password reset
- Correct client IP behind the hosting proxy (`--proxy-headers` with trusted proxies) — rate limits and IP hashes depend on it
- Retention policy for `security_events` (90 days)
- CodeQL, OWASP ZAP scan against the deployed app, written report
- Optional 2FA (TOTP)
