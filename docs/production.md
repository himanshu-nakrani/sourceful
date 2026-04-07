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

## Compatibility notes
- SQLite remains supported for local development only.
- Reprocessing a completed document reuses stored chunks unless the latest failed job still has original payload bytes.
- BYOK keys are provided per request. Queued jobs temporarily store the provider key until the worker completes the job.
