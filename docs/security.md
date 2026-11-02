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
- Planned: IP-based rate limiting on auth routes.

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

### Error handling
- Validation errors return field + message only, never the submitted value.
- Database errors return a generic `503`; details stay server-side.
- External API text is rendered as plain text only (XSS).

## Known gaps / planned
- IP rate limiting on `/auth/*`
- Email verification and password reset
- Security headers (CSP, HSTS, X-Frame-Options) and CORS allowlist
- Correct client IP behind the hosting proxy (`--proxy-headers` with trusted proxies)
- Retention policy for `security_events` (90 days)
- Automated security tests, CI scanning (gitleaks, Bandit, pip-audit, CodeQL), OWASP ZAP report
