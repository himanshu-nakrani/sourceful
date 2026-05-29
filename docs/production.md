# Production Notes

## Deployment shape
Recommended deployment for self-hosted usage:
- `web` exposed to users
- `api` internal or reverse-proxied
- `worker` always on
- `postgres` with persistent storage

## Operational checklist
- Set `DATABASE_URL` to PostgreSQL in production.
- Run at least one `worker` instance.
- Back up PostgreSQL regularly.
- Monitor `/ready` and `/metrics`.

## Upgrades
1. Pull the new release.
2. Rebuild images.
3. Restart `api` and `worker` so schema startup checks run against the latest code.
4. Verify `/ready` before opening traffic.

### One-time: anonymous session re-keying (Fix #5)

Releases that introduce signed anonymous sessions change how anonymous data is
scoped. Previously the owner key was `anon:<X-Client-Session header>`; it is now
`anon:<hmac(header)>`, signed with `ANON_SESSION_SECRET`. This secret is
**required in production** (when `DATABASE_URL` is set) — the API refuses to
start without it. Local SQLite dev falls back to `DEFAULT_SUPERUSER_PASSWORD`.
Anonymous data created before this release stays keyed by the old scheme and is
invisible to its owner until re-keyed.

If you have existing anonymous data to preserve:

1. Set `ANON_SESSION_SECRET` to its final production value first (changing it
   later re-scopes anonymous data again).
2. Dry-run the migration to review the plan:
   `python -m backend.scripts.migrate_anon_scopes`
3. Apply it once: `python -m backend.scripts.migrate_anon_scopes --apply`

The script is safe to re-run — already-signed scopes are skipped. If you do not
need to preserve anonymous data, skip this; old rows simply become orphaned.

## Compatibility notes
- SQLite remains supported for local development only.
- Reprocessing a completed document reuses stored chunks unless the latest failed job still has original payload bytes.
- BYOK keys are provided per request. Queued jobs temporarily store the provider key until the worker completes the job.
