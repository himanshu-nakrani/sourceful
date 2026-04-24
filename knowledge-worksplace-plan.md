# VNext Knowledge Workspace Plan

## Product Intent
Evolve the app from a single-document QA workflow into a phased **knowledge workspace** product while preserving the existing self-hosted, BYOK, worker-backed architecture.

This document is intended to be implementation-ready. Each phase includes concrete product goals, backend tasks, frontend tasks, data/API tasks, and validation work so engineering can execute the roadmap without re-planning the shape of the release.

## Summary
- Treat `workspace` as the new top-level product object.
- Preserve backward compatibility for existing uploads, chats, and session scoping during migration.
- Make Phase 1 the first candidate release by shipping workspace-based multi-source retrieval.
- Keep the product self-hostable, BYOK-first, and durable through the existing API + worker model.
- If scope tightens, cut collaboration work before cutting workspace-based multi-source retrieval.

## Phase 0: Foundations and Migration Safety
### Goal
Introduce the workspace model without breaking current single-document behavior or existing user data.

### Product outcomes
- Every user/session gets a default personal workspace.
- Existing documents and conversations continue to work after upgrade.
- Legacy flows keep functioning even before the full workspace UI is enabled.

### Data and schema tasks
- Add a `workspaces` table with:
  - `id`
  - `owner_id`
  - `name`
  - `description`
  - `visibility`
  - `archived`
  - `created_at`
  - `updated_at`
- Add a `workspace_members` table with:
  - `id`
  - `workspace_id`
  - `user_id`
  - `role`
  - `created_at`
  - `updated_at`
- Add a `workspace_sources` table with:
  - `id`
  - `workspace_id`
  - `source_type`
  - `document_id`
  - `source_title`
  - `source_url`
  - `metadata_json`
  - `created_at`
  - `updated_at`
- Add `workspace_id` to:
  - `documents`
  - `conversations`
- Keep `messages` and `document_jobs` linked through existing entities rather than duplicating workspace linkage.
- Add indexes for:
  - `workspaces.owner_id`
  - `workspace_members.workspace_id`
  - `workspace_members.user_id`
  - `workspace_sources.workspace_id`
  - `documents.workspace_id`
  - `conversations.workspace_id`

### Migration tasks
- Create one default personal workspace for every existing `owner_id` already represented in documents or conversations.
- Backfill all existing documents into that default workspace.
- Backfill all existing conversations into the same workspace as their document.
- For orphaned edge cases:
  - create or reuse the owner default workspace
  - attach records there
- Make the migration idempotent so repeated startup checks do not duplicate workspaces or memberships.
- Preserve current auth/session scoping semantics by continuing to use `owner_id` as the primary ownership boundary during Phase 0.

### Backend tasks
- Update Pydantic models and API response models to include `workspace_id` where relevant.
- Add workspace CRUD endpoints:
  - `POST /api/workspaces`
  - `GET /api/workspaces`
  - `GET /api/workspaces/{workspace_id}`
  - `PATCH /api/workspaces/{workspace_id}`
- Implement default-workspace lookup helpers in router dependencies or service functions.
- Automatically bind legacy ingest/chat/conversation flows to the caller's default workspace when no explicit workspace is provided.
- Ensure document deletion continues to cascade safely via existing foreign keys and workspace-linked ownership.
- Add a compatibility path so existing routes can still function before the full workspace-aware frontend ships.

### Frontend tasks
- Add workspace state to the client store:
  - available workspaces
  - active workspace id
  - loading/error state
- On app bootstrap, load workspaces and select the default workspace automatically.
- Keep the current document/chat UI functional by deriving the active workspace transparently.
- Add a hidden or feature-flagged compatibility mode if the workspace UI is not ready yet.
- Add a clear fallback if workspace loading fails:
  - retry
  - surface error
  - avoid leaving the app in a broken empty state

### Validation tasks
- Add migration tests that verify:
  - old data appears in a default workspace after upgrade
  - existing conversations remain accessible
  - document deletion still cascades safely inside workspace scope
- Add route tests that verify:
  - every document response includes the correct `workspace_id`
  - every conversation response includes the correct `workspace_id`
  - no route returns cross-workspace data
- Manually verify:
  - an existing user can still upload a file
  - select a document
  - ask a question
  - reprocess a document
  - export a conversation

### Acceptance criteria
- Existing users can still upload, select, and chat with documents after upgrade.
- Every document and conversation belongs to exactly one workspace.
- No API route returns cross-workspace data.

## Phase 1: Workspace + Multi-Source MVP
### Goal
Ship the first visible product leap by making the workspace the main interaction model and enabling retrieval across multiple sources.

### Product outcomes
- Users can create and switch workspaces.
- Users can upload multiple files and import at least one URL into the same workspace.
- Chat works across all ready sources in the workspace by default.
- Users can inspect evidence grouped by source rather than seeing a flat citation list.

### Frontend information architecture tasks
- Replace the current document-first sidebar hierarchy with:
  - Workspaces
  - Sources
  - Chats
- Add a workspace switcher in the sidebar header.
- Add a create-workspace flow:
  - inline modal or panel
  - name required
  - optional description
- Group sources beneath the active workspace.
- Show source status badges:
  - queued
  - processing
  - ready
  - error
- Distinguish source type visually:
  - file
  - url
  - note placeholder
- Update the empty state to invite users to:
  - create/select a workspace
  - add sources
  - start a chat

### Data and API tasks
- Introduce workspace-aware request shapes:
  - chat requests require `workspace_id`
  - allow optional `source_ids[]` to narrow retrieval
- Update list routes to accept or derive workspace scope where appropriate.
- Add source-oriented endpoints:
  - `GET /api/workspaces/{workspace_id}/sources`
  - `POST /api/workspaces/{workspace_id}/sources/url`
  - optional `GET /api/workspaces/{workspace_id}/sources/{source_id}`
- Keep file uploads on the existing ingestion pipeline but attach the created document/source to the selected workspace.
- Store source metadata:
  - title
  - source type
  - canonical URL
  - MIME type when available
  - last fetched time
  - indexing status

### Backend tasks
- Update chat retrieval logic to fetch across all ready sources in the workspace by default.
- Support `source_ids[]` in chat and restrict retrieval to those selected sources when provided.
- Ensure multi-source retrieval can return citations from different documents in a single answer.
- Reuse the durable worker/job model for URL ingestion:
  - fetch remote content
  - detect HTML vs PDF
  - extract text
  - chunk
  - embed
  - persist as document chunks linked through a workspace source
- Add URL ingestion validation:
  - supported protocols
  - content length limits
  - fetch timeout handling
  - unsupported content errors
- Add reprocess support for URL-backed sources.
- Ensure conversations are workspace-scoped, not single-document scoped only.
- Preserve optional single-document behavior by allowing the UI to pass a narrowed `source_ids[]` selection containing one source.

### Frontend tasks
- Update upload flows so files attach to the active workspace.
- Add URL import UI:
  - input field
  - validation
  - submit state
  - durable job progress
- Add source filtering inside the chat composer:
  - all sources in workspace
  - selected subset
- Allow users to start a new chat for the workspace even when no single document is selected.
- Update conversation list semantics from document-specific to workspace-specific.
- Replace the current simple source card with an evidence panel v1:
  - group citations by source document
  - display source title
  - show page number and chunk identifier consistently
  - show excerpt and relevance signal
  - support clicking a citation to jump to chunk preview
- Update chunk preview to load by source/document context from the workspace view.

### Validation tasks
- Add backend tests that verify:
  - workspace-wide retrieval spans multiple sources
  - `source_ids[]` restricts retrieval correctly
  - URL ingestion produces queryable chunks
  - workspace chat can mix citations from multiple documents
- Add frontend/manual verification for:
  - create workspace
  - upload 2+ files
  - import 1 URL
  - ask one question spanning all sources
  - confirm evidence from multiple sources appears
  - narrow retrieval to one selected source and confirm the answer changes accordingly

### Acceptance criteria
- Users can chat across multiple sources in one workspace.
- URL sources are durable and reprocessable.
- Evidence can be inspected per source, not only as a flat list.

## Phase 2: Analysis Workflows and Saved Knowledge
### Goal
Make the workspace cumulative and task-oriented rather than a generic chat surface.

### Product outcomes
- Users can run distinct analysis modes with predictable outputs.
- Users can save important answers and notes back into the workspace.
- Saved knowledge becomes reusable context for future chats without losing source transparency.

### Data and schema tasks
- Add a workspace artifact or notes table, for example `workspace_artifacts`, with:
  - `id`
  - `workspace_id`
  - `artifact_type`
  - `title`
  - `content`
  - `metadata_json`
  - `source_message_id`
  - `created_by`
  - `created_at`
  - `updated_at`
- Support artifact types:
  - `user_note`
  - `saved_answer`
  - `saved_brief`
  - `extraction_result`
- Add optional linkage from artifacts back to originating messages or sources for traceability.

### API and backend tasks
- Add analysis modes to the chat/composer API:
  - `ask`
  - `compare`
  - `extract`
  - `brief`
- Define output contracts:
  - `ask`: grounded answer with citations
  - `compare`: structured similarities/differences across sources
  - `extract`: normalized field extraction or targeted bullet output
  - `brief`: executive summary, study guide, or briefing layout
- Add artifact endpoints:
  - create note/artifact
  - list workspace artifacts
  - update artifact
  - delete artifact
- Add “save assistant response” support by converting a response into a stored artifact.
- Expand retrieval so saved notes and saved answers can be included in future workspace context.
- Distinguish saved artifacts from uploaded sources in retrieval metadata so citations stay interpretable.
- Define retrieval precedence rules:
  - uploaded sources remain primary evidence
  - saved artifacts are augmenting context
  - assistant-authored artifacts should not masquerade as original source documents

### Frontend tasks
- Add mode controls to the composer with clear defaults.
- Render mode-specific outputs:
  - `compare`: sections or tables by source
  - `extract`: copyable structured blocks
  - `brief`: executive-style outline with citations
- Add “Save to workspace” on assistant responses.
- Add user-authored notes in the workspace navigation.
- Add an artifacts/notes view in the sidebar or right panel.
- Allow users to reuse artifacts in later chats by:
  - including them implicitly via workspace retrieval
  - optionally filtering or selecting them
- Add compare UX that supports source selection before execution.
- Add extract UX that preserves citations for each extracted field or section.
- Carry over the Phase 1 source-filter chat composer work:
  - per-source checkboxes inside the chat composer
  - wire the selection through to the `source_ids[]` chat request field (backend already accepts it)
  - keep "all sources in workspace" as the default so no regression for users relying on the current behavior
- Add optional workspace overview surfaces if capacity allows:
  - auto-generated workspace summary
  - source/topic summary cards
- Defer mind-map style visualization unless Phase 2 has room after core artifact work is stable.

### Validation tasks
- Add tests that verify:
  - saved artifacts become available in later chats
  - compare mode pulls evidence from at least two sources
  - extract mode remains grounded and reproducible
  - briefs can be saved and reused as context
  - artifact retrieval does not break citation trust
- Manually verify:
  - save a response to workspace
  - create a user note
  - ask a follow-up that benefits from the saved artifact
  - compare two sources
  - run extract mode and copy/export the result

### Acceptance criteria
- Users can accumulate knowledge over time inside a workspace.
- Modes produce clearly different outputs and behaviors.
- Saved items improve future chats without breaking citation trust.

## Phase 3: Collaboration and Sync
### Goal
Make the workspace usable by teams and prepare the data model for durable sync and future connectors.

### Product outcomes
- Workspaces support roles and invitations.
- Editors can manage content while viewers remain read-only.
- URL sources can be refreshed and tracked durably.
- The architecture is ready for future connector support without forcing another schema redesign.

### Data and schema tasks
- Formalize membership roles:
  - `owner`
  - `editor`
  - `viewer`
- Add URL source sync fields:
  - `last_synced_at`
  - `last_sync_status`
  - `last_sync_error`
  - `next_sync_at` if scheduled refresh is introduced later
- Add source sync history if needed, for example `workspace_source_sync_runs`, to record:
  - source
  - start/end time
  - status
  - error message
  - changed checksum/version info
- Ensure audit-friendly timestamps exist for membership and content changes.

### Backend tasks
- Enforce permissions on workspace, source, note, artifact, and conversation routes.
- Add invite/member management endpoints:
  - list members
  - invite/add member
  - update role
  - remove member
- Restrict actions by role:
  - owner: full control
  - editor: manage sources, notes, and chats
  - viewer: chat and read only
- Add URL resync action that reuses the worker/job path instead of creating a one-off background flow.
- Track sync history and expose it to the UI.
- Evolve analytics to include per-workspace health and usage metrics:
  - source counts
  - ready/error counts
  - recent chat activity
  - recent artifact activity
- Formalize a source adapter interface so future connectors such as Google Drive or Slack can plug in without changing core workspace/source tables.
- Do not implement broad connectors in this phase unless reprioritized separately.

### Frontend tasks
- Add membership UI:
  - member list
  - role badge
  - invite flow
  - role editor
- Add sharing UX:
  - owner can invite users
  - editors can see members
  - viewers see workspace read-only controls
- Add recent activity surfaces:
  - uploads
  - saved briefs
  - active chats
- Add URL resync action and display:
  - sync state
  - last synced time
  - refresh failures
- Add role-aware UI disabling:
  - viewers cannot edit content
  - editors cannot manage ownership
- Update workspace analytics views to focus on the active workspace first, with global/shared analytics remaining secondary.

### Validation tasks
- Add permission tests that verify:
  - viewers cannot edit workspace content
  - editors cannot manage ownership
  - retrieval only uses sources visible within workspace permissions
- Add sync tests that verify:
  - URL refresh is durable
  - sync failures are surfaced cleanly
  - refreshed content updates retrieval corpus without data leakage
- Add end-to-end validation for:
  - owner creates workspace
  - editor adds sources
  - viewer chats against them
  - URL source refresh updates retrieval safely

### Acceptance criteria
- Shared workspaces behave predictably with role boundaries.
- URL refresh is durable and observable.
- The schema is ready for future connector work.

## Cross-Phase Technical Decisions
- Keep the app self-hostable and BYOK-first.
- Preserve worker-backed ingestion as the only durable async path.
- Treat `workspace` as the new top-level product object.
- Keep source support phased:
  - Phase 1: file + URL
  - Phase 2: note + saved answer
  - Phase 3: refresh/sync + connector-ready adapters
- Do not prioritize new model/provider controls ahead of workspace/product depth.
- Prefer backward-compatible API evolution where feasible, but allow cleaner v2-style chat request changes if that lowers long-term complexity.
- Preserve the current split between Next.js frontend and FastAPI backend.
- Avoid broad connector implementation before the workspace/source model is stable.

## Test Plan
### Per-phase checks
- Migration and backfill correctness.
- Multi-source retrieval correctness.
- URL ingestion durability.
- Citation and evidence integrity.
- Saved artifact retrieval behavior.
- Role-based access control.
- Worker/job visibility for every async source action.
- Manual end-to-end verification of upload, retrieval, compare, save, share, and refresh flows.

### Suggested execution order
- Run targeted backend tests for each touched subsystem first.
- Run full backend test suite when changing shared models, migrations, retrieval, or permissions.
- Run frontend lint and build for workspace UI and routing/state changes.
- Run full-stack verification with frontend, API, and worker together for:
  - file upload
  - URL import
  - retrieval
  - reprocess/resync
  - evidence inspection
  - collaboration flows

## Acceptance Criteria by Phase
### Phase 0
- Existing users can still upload, select, and chat with documents after upgrade.
- Every document and conversation belongs to exactly one workspace.
- No API route returns cross-workspace data.

### Phase 1
- Users can chat across multiple sources in one workspace.
- URL sources are durable and reprocessable.
- Evidence can be inspected per source, not only as a flat list.

### Phase 2
- Users can accumulate knowledge over time inside a workspace.
- Modes produce clearly different outputs and behaviors.
- Saved items improve future chats without breaking citation trust.

### Phase 3
- Shared workspaces behave predictably with role boundaries.
- URL refresh is durable and observable.
- The schema is ready for future connector work.

## Open Assumptions
- This plan document lives at `docs/vnext-knowledge-workspace-plan.md`.
- The document is intended to be implementation-ready, not just strategic.
- Phase 1 is the first candidate release.
- Current auth/session scoping remains the ownership boundary through migration, with collaboration layered on later.
- If schedule compresses, cut collaboration before cutting workspace-based multi-source retrieval.
