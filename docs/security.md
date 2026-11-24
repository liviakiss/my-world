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

### Email verification
- Signup sends a confirmation link; the token is 256 random bits, stored only as a SHA-256 hash, valid for 24 hours and usable once.
- Asking for a new link invalidates every older one.
- Signing up with an email that already has an account sends that owner a warning email instead of a link, so the API response stays identical (no account enumeration) and only the inbox owner learns the truth.
- Emails are sent in a background task after the response, so response time does not reveal which branch ran, and an email provider outage never breaks signup.
- The link opens a frontend page that POSTs the token; a GET would let email security scanners that pre-open links consume tokens.
- Reminder emails go only to verified addresses, so the app cannot be used to send mail to someone else's inbox.

### Account lifecycle
- **Password reset**: the same answer whether or not the email has an account; the link is valid for 30 minutes, works once, and is useless for anything else (tokens carry a purpose). Completing a reset logs out every session, clears any lockout and emails a "password changed" notice.
- **Re-authentication**: changing the password or email and deleting the account all require the current password, even with a valid session. A stolen session alone cannot take over or destroy an account; failed attempts are logged (`reauth_failed`) and rate limited (5/min).
- **Password change** logs out every other device but keeps the current one; **log out everywhere** revokes every session.
- **Email change** only takes effect after the link sent to the *new* address is clicked, and the *old* address is told (with the new one masked). The response is the same whether the new address is free or taken.
- **Account deletion** removes the account and all personal data by database cascade (shelf, custom works, follows, activity events, tokens, reminders); security events stay for incident review but lose the link to the person.
- **Data export** (GDPR right of access) returns everything stored about the user as a JSON download, without password hashes, token hashes or IP hashes, and is rate limited (3/min).
- Known limit: access tokens are stateless, so a revoked session can keep working for up to 15 minutes until its access token expires.

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
- Tests use short tracebacks (`--tb=short`): full tracebacks print function arguments, which once showed a database password in local test output.
- All secrets in environment variables, typed as `SecretStr` (masked in logs and errors).
- App refuses to start if a secret is missing or shorter than 32 characters (fail fast).
- `alembic.ini` contains no credentials.
- Database connection requires TLS (`sslmode=require`) and channel binding.

### Authorization (shelf data)
- Every shelf query is scoped by the logged-in user's ID inside the SQL `WHERE` clause (`Entry.user_id == user.id`), never filtered afterwards in Python.
- Another user's entry returns `404 Not Found`, not `403 Forbidden`: the API does not confirm that the ID exists (protects against IDOR probing).
- Custom works are private to their creator; catalogue works (from public APIs) are visible to everyone.
- Request bodies use explicit schemas with `extra="forbid"`: fields such as `user_id`, `created_by_user_id` or `cover_url` cannot be smuggled in (mass assignment).
- Users cannot set `cover_url` on custom works, so no attacker-chosen URLs are stored or loaded by other browsers.
- Personal statistics are computed only from rows filtered by the logged-in user's ID; the one raw SQL query uses a bound parameter (`:user_id`), never string formatting.
- The spin wheel picks only from the user's own entries.
- Write endpoints are rate limited (60/min) and each user can create at most 1,000 custom works, so one account cannot flood the database.
- Input limits mirror the database CHECK constraints (rating 0.5–5 in half steps, progress ≥ 0 and ≤ the work's size, notes ≤ 5,000 characters, finish date not before start date): the API rejects bad data with a clear `422`, the database is the safety net.

### External data (catalogue search)
- The server only ever calls fixed hosts (`openlibrary.org`, `api.themoviedb.org`); users never supply a URL, so the API cannot be used to reach internal addresses (SSRF).
- Redirects are not followed, every request has a 5-second timeout and responses over 2 MB are refused.
- IDs sent to upstream APIs are checked against strict patterns first (`OL123W`, `tv:123`), so input like `../../admin` never reaches a URL path.
- Everything that comes back is treated as untrusted: HTML tags stripped, text trimmed to column limits, lists capped, numbers range-checked, cover URLs rebuilt by the server and accepted only as `https` on the provider's image host.
- The TMDB token is sent in the `Authorization` header, never in the URL, so it does not end up in access logs.
- Search requires login and is rate limited (30/min) to protect the shared API quota.
- Upstream failures return a generic `502`; the details go to the server log only.
- Imported works are cached in the database and shared, so each title is fetched from the provider once.

### Reminder emails
- Plain-text only: titles from external catalogues are never rendered as HTML in emails.
- Subjects are forced onto one line, so a title containing line breaks cannot add email headers (header injection).
- Each reminder is recorded in `notifications` with a unique key, so it is sent at most once per release even if the job runs repeatedly; a failed send is not recorded and is retried on the next run.
- Users can switch reminder emails off at any time; production refuses to start without a real email provider configured, and the provider key is sent in a header.

### Release tracking job
- Runs as a separate command (`python -m app.jobs.check_releases`), not inside a web request, so slow providers never block users.
- Checks each followed title at most once every 20 hours and in batches of 200, regardless of how many users follow it: the provider quota grows with the number of titles, not users.
- One failing title is logged and skipped; the job commits after each title, so a crash halfway keeps the work already done.
- A user's own release date always wins over a found one; the found date is only shown as a suggestion.
- Follows are scoped to the logged-in user like shelf entries (404 for anyone else's), capped at 500 per user, and removed when the account is deleted.

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
- Automated tests (`backend/tests`) prove each control: one user cannot read, change, delete or shelve another user's data, identical responses for taken/unknown emails, no password echo, lockout, cookie flags, token rotation, reuse detection, forged / expired / `alg: none` JWTs rejected, rate limits, headers and CORS.
- Tests run against a separate database; the suite refuses to start if it points at the development database.
- Supply chain incident (Nov 2026): pip-audit in CI flagged CVE-2026-128089 (`dnspython`) and CVE-2026-126360 (`opentelemetry-api`), both transitive dependencies; fixed by upgrading to the patched versions.
- CI on every push: tests against a fresh Postgres, gitleaks (secret scanning, full history), Bandit (static analysis), pip-audit (known-vulnerable dependencies). Dependabot keeps dependencies and actions updated.

## Known gaps / planned
- Email verification and password reset
- Correct client IP behind the hosting proxy (`--proxy-headers` with trusted proxies) — rate limits and IP hashes depend on it
- Retention policy for `security_events` (90 days)
- CodeQL, OWASP ZAP scan against the deployed app, written report
- Optional 2FA (TOTP)
