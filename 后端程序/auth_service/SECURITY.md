# Authentication hardening

Run the schema upgrade before deploying this version:

```powershell
Set-Location D:\前端知识\05_网页前后端程序\后端程序\auth_service
alembic upgrade head
```

The service now enforces a 7-day refresh idle timeout (`REFRESH_TOKEN_DAYS`) and a 30-day absolute session lifetime (`REFRESH_ABSOLUTE_DAYS`). Refresh rotation can never move the absolute expiry forward.

Production must provide Redis. Rate limits use one Lua operation to increment and attach/repair expiry atomically; an unavailable Redis service returns 503 rather than silently falling back to one-process limiting.

Outbox workers only deliver a conditionally claimed item. The states are `pending`, `retry`, `sent`, and terminal `dead`; retry waits use bounded exponential backoff. Run `python -m app.workers` from a scheduler or worker process.

Login requires a one-time five-character image captcha; registration does not use this captcha because account activation is completed by its email verification code. The server stores only an HMAC of a captcha answer; a challenge expires after five minutes, is consumed after success, and allows at most five guesses.

MFA is temporarily disabled (`MFA_ENABLED=false`). Existing MFA records are retained but ignored during login and password reset. Set `MFA_ENABLED=true` only after restoring the account-security UI.

`POST /api/auth/password-reset/request` and `/password-reset/confirm` use a reset-specific code table and invalidate all existing sessions after a successful reset.

All write requests require the existing CSRF header. Password-reset requests deliberately disclose whether an email is registered: an unregistered address returns `404` with a registration prompt, as required by this learning project. Do not reuse this behavior in a public production system where account enumeration is a concern.

Registration, password reset, and authenticated password change all reject passwords found in public breach dumps via the HaveIBeenPwned k-anonymity API (only the first five SHA-1 characters leave the service; responses are cached for 24h with a bounded LRU cache). Production requires `PWNED_CHECK_ENABLED=true` and `PWNED_CHECK_STRICT=true`, so an unavailable breach service fails closed (503). A new password may not equal the current password or any of the last `PASSWORD_HISTORY_COUNT` (default 5) archived hashes stored in `password_history`. Password change is a two-step flow: the authenticated user supplies the current password to request a six-digit email code, then submits the code with the new password. A successful change and a password reset both archive the old hash, revoke every old session, and issue a fresh current session only after the change succeeds.
