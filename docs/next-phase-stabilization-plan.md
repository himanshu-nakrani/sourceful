# Next Phase: Stabilization + Workspace Foundations

## Summary

Ship a low-risk foundation release that fixes current product and operational gaps while introducing Phase 0 workspace support behind compatible APIs. Existing upload, ingestion, chat, reprocess, export, and document-scoped UI behavior must keep working throughout.

## Key Changes

- Add workspace schema foundations: `workspaces`, `workspace_members`, `workspace_sources`, plus `workspace_id` on `documents` and `conversations`; bump SQLite/Postgres schema versions and make startup migrations idempotent.
- Backfill one default personal workspace per existing `owner_id`; attach all existing documents and conversations to that workspace.
- Add workspace APIs: list, get, create, rename/update; automatically create or return the caller's default workspace when needed.
- Extend document, conversation, ingest, and chat responses with `workspace_id`, while keeping current `document_id` request paths valid.
- Update backend queries so all document, conversation, chat, and job access remains scoped by `owner_id` and, where provided, `workspace_id`.
- Add frontend workspace state: load workspaces after auth, select the default workspace, pass active `workspace_id` during ingest/chat/list flows, and keep the current document-first UI as the visible compatibility experience.
- Improve current stability while touching these paths: clearer empty/error states for missing worker readiness, failed ingestion, provider-key requirements, and conversation/document mismatch errors.

## Implementation Notes

- Treat this as Phase 0, not Phase 1: no URL ingestion, multi-source retrieval, collaboration UI, or source filtering yet.
- Preserve existing endpoints such as `/api/ingest`, `/api/documents`, `/api/chat`, and `/api/conversations`; add optional workspace awareness rather than replacing them.
- Default behavior: if no `workspace_id` is supplied, use the caller's default workspace.
- Workspace membership is created now for future permissions, but enforcement remains equivalent to current `owner_id` scoping.
- Do not modify `legacy/`.

## Test Plan

- Backend migration tests: fresh DB, existing DB backfill, repeated startup idempotency, documents/conversations assigned exactly one workspace.
- Backend route tests: workspace list/create/update, document responses include `workspace_id`, conversations include `workspace_id`, legacy requests without `workspace_id` still work.
- Regression tests: full ingest -> worker process -> chat -> conversation export -> reprocess -> delete flow.
- Isolation tests: two client sessions/users cannot see each other's workspaces, documents, conversations, chunks, or jobs.
- Frontend checks: `npm run lint`, `npm run build`, and manual browser verification of login, upload, indexing progress, chat, reprocess, export, and workspace bootstrap.
- Full-stack validation: run API, worker, and frontend together before signoff because ingestion durability depends on the worker.

## Assumptions

- The next phase is Stabilization + Phase 0 workspace foundations.
- Workspace UI remains minimal and transparent in this phase; the visible app may still look document-first.
- Phase 1 features from `docs/vnext-knowledge-workspace-plan.md` are intentionally deferred until Phase 0 is proven stable.
- Existing `.Jules/palette.md` changes are unrelated and should be left untouched.
