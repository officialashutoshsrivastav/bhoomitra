# Security

## Authentication

* Passwords hashed with **bcrypt**; minimum 10 characters, letters plus digits, common passwords
  rejected. Inputs longer than the bcrypt limit are handled safely.
* **Access tokens** (JWT, default 30 min) carry `sub`, `jti`, `iat`, `email`, `su` and `pv` — a
  password-version stamp. Changing a password changes `pv`, so every previously issued access token
  is rejected immediately.
* **Refresh tokens** (default 14 days) are opaque, stored hashed, rotated on every use and delivered
  both in the body and as an `HttpOnly`, `SameSite=Lax`, `Secure`-in-production cookie. Presenting a
  rotated token is treated as theft: the entire token family is revoked (`token_reuse`).
* **Lockout** — five failed attempts lock the account for a cool-down period; attempts are recorded
  with IP and user agent. Login responses never reveal whether the email exists.
* Password reset and activation tokens are single-use, hashed at rest and time-limited.

## Authorisation

Thirteen roles map onto ~46 fine-grained permissions (`document.create`, `gis.analyze`,
`simulation.approve`, `admin.manage_users`, …). Routes declare requirements
(`require_permissions(P.X)`); services additionally enforce ownership, organisation scope,
workspace membership and publication state. Denials return 403 with the required permission listed,
and the frontend hides what the session cannot use — but the server is the authority.

## Uploads

Checksum, extension check, **content-based MIME sniffing** (declared types are never trusted), size
limit (`MAX_UPLOAD_MB`), a malware-scanner hook (the EICAR test string is rejected out of the box)
and storage outside the web root. Downloads are streamed with
`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` and a checksum header.

## Transport and headers

Security headers on every response: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and HSTS in production.
CORS is an explicit allow-list (`CORS_ORIGINS`) with credentials enabled. Auth endpoints are rate
limited (`RATE_LIMIT_AUTH_PER_MINUTE`).

## Audit

`audit_logs` is append-only: actor, action, resource type/id, result (success/failure/denied), IP,
user agent, request ID and a JSON detail. Reading it requires `audit.read`. Every state change —
create, upload, submit, review, publish, archive, role change, approval decision, settings change —
is recorded.

## Data protection

SQL is parameterised through SQLAlchemy; GeoJSON is parsed by PostGIS, never string-concatenated.
Secrets live only in environment variables and are redacted in `/admin/settings`. Rendered snippets
are sanitised before display. Demo data is clearly flagged so it can never be mistaken for official
statistics.

## Deployment checklist

- [ ] Generate a new `JWT_SECRET_KEY` (≥32 random characters).
- [ ] Change `BOOTSTRAP_SUPERADMIN_PASSWORD` and delete or disable all demo accounts.
- [ ] Set `DEMO_DATA_ENABLED=false` and load real boundaries and statistics.
- [ ] Set `APP_ENV=production`, `DEBUG=false`, `LOG_JSON=true`.
- [ ] Terminate TLS at the proxy; restrict `CORS_ORIGINS` to the real front-end origin.
- [ ] Keep the database on a private network; enable automated backups and PITR.
- [ ] Point `STORAGE_BACKEND=s3` at object storage with versioning and server-side encryption.
- [ ] Enable a real malware scanner in front of the upload hook.
- [ ] Ship logs and audit records to a central SIEM; alert on `denied` and failed-login spikes.
- [ ] Review roles quarterly; disable dormant accounts.
