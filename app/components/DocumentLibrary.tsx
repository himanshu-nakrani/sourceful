"use client";

import { useMemo, useState, type CSSProperties } from "react";
import { RotateCw, Search, Settings2, Upload } from "lucide-react";
import type { DocumentInfo, JobStatus } from "../lib/api";
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";

interface DocumentLibraryProps {
  onUploadClick: () => void;
}

type DocumentLibraryStatusFilter = "all" | "ready" | "processing" | "attention";
type DocumentLibrarySortOrder = "newest" | "name" | "oldest";

const DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const STATUS_LABELS: Record<JobStatus, string> = {
  ready: "Ready",
  processing: "Processing",
  queued: "Queued",
  error: "Needs attention",
};

const MIME_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "application/msword": "DOC",
  "application/rtf": "RTF",
  "application/vnd.ms-powerpoint": "PPT",
  "application/vnd.ms-excel": "XLS",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PPTX",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
  "text/csv": "CSV",
  "text/html": "HTML",
  "text/markdown": "MD",
  "text/plain": "TXT",
};

function documentKind(document: DocumentInfo): string {
  const extension = document.filename.match(/\.([a-z0-9]+)$/i)?.[1];
  if (extension) return extension.toUpperCase();

  const mimeType = document.mime_type?.toLowerCase().split(";")[0].trim();
  if (!mimeType) return "File";
  return (
    MIME_LABELS[mimeType] ??
    mimeType.split("/").pop()?.replace(/^x-/, "").toUpperCase() ??
    "File"
  );
}

function documentDate(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return DATE_FORMATTER.format(date);
}

function pageCount(document: DocumentInfo): string | null {
  if (
    typeof document.page_count !== "number" ||
    !Number.isFinite(document.page_count) ||
    document.page_count <= 0
  ) {
    return null;
  }
  return `${new Intl.NumberFormat("en-US").format(document.page_count)} ${document.page_count === 1 ? "page" : "pages"}`;
}

export default function DocumentLibrary({ onUploadClick }: DocumentLibraryProps) {
  const { state, dispatch } = useStore();
  const {
    documents,
    documentsLoading,
    documentsError,
    refreshDocuments,
    selectDocument,
  } = useServerState();
  const { settings, activeWorkspaceId } = state;
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<DocumentLibraryStatusFilter>("all");
  const [sortOrder, setSortOrder] = useState<DocumentLibrarySortOrder>("newest");

  const workspaceDocuments = useMemo(() => {
    if (!activeWorkspaceId) return documents;
    return documents.filter(
      (document) =>
        !document.workspace_id || document.workspace_id === activeWorkspaceId
    );
  }, [documents, activeWorkspaceId]);
  const visibleDocuments = useMemo(() => {
    const term = search.trim().toLowerCase();
    return workspaceDocuments
      .filter((document) => {
        const matchesSearch =
          !term || document.filename.toLowerCase().includes(term);
        const documentStatus = document.status;
        const matchesStatus =
          statusFilter === "all" ||
          (statusFilter === "ready" && documentStatus === "ready") ||
          (statusFilter === "processing" &&
            (documentStatus === "processing" || documentStatus === "queued")) ||
          (statusFilter === "attention" && documentStatus === "error");
        return matchesSearch && matchesStatus;
      })
      .sort((first, second) => {
        if (sortOrder === "name") {
          return first.filename.localeCompare(second.filename, "en", {
            sensitivity: "base",
          });
        }

        const firstAdded = Date.parse(first.created_at ?? "");
        const secondAdded = Date.parse(second.created_at ?? "");
        if (!Number.isFinite(firstAdded)) {
          return Number.isFinite(secondAdded) ? 1 : 0;
        }
        if (!Number.isFinite(secondAdded)) return -1;
        return sortOrder === "newest"
          ? secondAdded - firstAdded
          : firstAdded - secondAdded;
      });
  }, [workspaceDocuments, search, statusFilter, sortOrder]);
  const hasActiveFilters = search.trim().length > 0 || statusFilter !== "all";

  const hasProviderKey = Boolean(settings.providerApiKey?.trim());
  const isEmptyCollection =
    !documentsLoading && !documentsError && workspaceDocuments.length === 0;
  const countLabel =
    documentsLoading && workspaceDocuments.length === 0
      ? "Loading"
      : documentsError && workspaceDocuments.length === 0
        ? "Unavailable"
        : `${workspaceDocuments.length} ${workspaceDocuments.length === 1 ? "document" : "documents"}`;

  const handlePrimaryAction = () => {
    if (!hasProviderKey) {
      dispatch({ type: "SET_SETTINGS_OPEN", payload: true });
      return;
    }
    onUploadClick();
  };

  const primaryActionStyle: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    minHeight: 40,
    padding: "0 15px",
    border: "1px solid transparent",
    borderRadius: 7,
    backgroundColor: "var(--accent, #a4412d)",
    color: "var(--accent-fg, #fff)",
    fontSize: 13,
    fontWeight: 550,
    cursor: "pointer",
  };

  return (
    <section className="document-library" aria-label="Document library">
      <div className="library-inner">
        <header className="library-header">
          <div className="library-heading">
            <div className="library-title-line">
              <h1 className="library-title editorial-heading">Library</h1>
              <span className="library-count" aria-live="polite">
                {countLabel}
              </span>
            </div>
          </div>
          {!isEmptyCollection && (
            <button
              type="button"
              className="library-primary"
              style={primaryActionStyle}
              onClick={handlePrimaryAction}
            >
              {hasProviderKey ? (
                <Upload size={15} strokeWidth={1.8} aria-hidden="true" />
              ) : (
                <Settings2 size={15} strokeWidth={1.8} aria-hidden="true" />
              )}
              <span>{hasProviderKey ? "Upload document" : "Connect provider"}</span>
            </button>
          )}
        </header>

        {documentsError && (
          <div className="library-error" role="alert">
            <div className="library-error-copy">
              <p className="library-error-title">Documents could not be loaded</p>
              <p>{documentsError}</p>
            </div>
            <button
              type="button"
              className="library-retry"
              onClick={() => void refreshDocuments()}
            >
              <RotateCw size={14} strokeWidth={1.8} aria-hidden="true" />
              <span>Try again</span>
            </button>
          </div>
        )}

        {isEmptyCollection ? (
          <section className="library-empty" aria-labelledby="library-empty-title">
            <p className="library-empty-kicker">No documents yet</p>
            <h2 id="library-empty-title">Start with a document.</h2>
            <p className="library-empty-description">
              {hasProviderKey
                ? "Upload a document to make it available as a source in chat."
                : "Connect OpenAI or Gemini to index documents."}
            </p>
            <button
              type="button"
              className="library-primary"
              style={primaryActionStyle}
              onClick={handlePrimaryAction}
            >
              {hasProviderKey ? (
                <Upload size={15} strokeWidth={1.8} aria-hidden="true" />
              ) : (
                <Settings2 size={15} strokeWidth={1.8} aria-hidden="true" />
              )}
              <span>{hasProviderKey ? "Upload document" : "Connect provider"}</span>
            </button>
          </section>
        ) : (
          <section className="library-browser" aria-label="Documents">
            {workspaceDocuments.length > 0 && (
              <div className="library-toolbar">
                <div className="library-controls">
                  <div className="library-search" role="search">
                    <label htmlFor="document-library-search" className="visually-hidden">
                      Search documents
                    </label>
                    <div className="library-search-control">
                      <Search size={15} strokeWidth={1.8} aria-hidden="true" />
                      <input
                        id="document-library-search"
                        type="search"
                        placeholder="Search by file name"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                      />
                    </div>
                  </div>
                  <label className="library-filter-control">
                    <span>Status</span>
                    <select
                      className="library-select"
                      value={statusFilter}
                      onChange={(event) =>
                        setStatusFilter(event.target.value as DocumentLibraryStatusFilter)
                      }
                    >
                      <option value="all">All</option>
                      <option value="ready">Ready</option>
                      <option value="processing">Processing (incl. queued)</option>
                      <option value="attention">Needs attention</option>
                    </select>
                  </label>
                  <label className="library-filter-control">
                    <span>Sort by</span>
                    <select
                      className="library-select"
                      value={sortOrder}
                      onChange={(event) =>
                        setSortOrder(event.target.value as DocumentLibrarySortOrder)
                      }
                    >
                      <option value="newest">Newest first</option>
                      <option value="name">Name A–Z</option>
                      <option value="oldest">Oldest first</option>
                    </select>
                  </label>
                </div>
                {hasActiveFilters && (
                  <span className="library-match-count" aria-live="polite">
                    {visibleDocuments.length} of {workspaceDocuments.length}{" "}
                    {workspaceDocuments.length === 1 ? "document" : "documents"}
                  </span>
                )}
                {hasActiveFilters && visibleDocuments.length === 0 && (
                  <button
                    type="button"
                    className="library-clear-filters"
                    onClick={() => {
                      setSearch("");
                      setStatusFilter("all");
                    }}
                  >
                    Clear filters
                  </button>
                )}
                {documentsLoading && (
                  <p className="library-refreshing" role="status">
                    Updating list…
                  </p>
                )}
              </div>
            )}

            {documentsLoading && workspaceDocuments.length === 0 && (
              <p className="library-loading" role="status">
                Loading documents…
              </p>
            )}

            {visibleDocuments.length > 0 && (
              <>
                <div className="library-columns" aria-hidden="true">
                  <span>Document</span>
                  <span>Format</span>
                  <span>Status</span>
                  <span>Added</span>
                </div>
                <ul className="library-rows" aria-label="Document results">
                  {visibleDocuments.map((document) => {
                    const kind = documentKind(document);
                    const pages = pageCount(document);
                    const date = documentDate(document.created_at);
                    const status = STATUS_LABELS[document.status];
                    const isActive = state.activeDocumentId === document.id;
                    const accessibleName = [
                      document.filename,
                      kind,
                      pages,
                      status,
                      date ? `Added ${date}` : null,
                    ]
                      .filter(Boolean)
                      .join(", ");

                    return (
                      <li key={document.id} className="library-row-item">
                        <button
                          type="button"
                          className="library-row"
                          aria-label={`Select ${accessibleName}`}
                          aria-pressed={isActive}
                          onClick={() => void selectDocument(document.id)}
                        >
                          <span className="library-file-cell">
                            <span className="library-file-name" title={document.filename}>
                              {document.filename}
                            </span>
                          </span>
                          <span className="library-format-cell">
                            <span className="library-format-content">
                              <span className="library-format-kind">
                                <span className="library-format-marker" aria-hidden="true" />
                                {kind}
                              </span>
                              {pages && (
                                <span className="library-page-count">{pages}</span>
                              )}
                            </span>
                          </span>
                          <span className="library-status-cell">
                            <span
                              className="library-status-mark"
                              data-status={document.status}
                              aria-hidden="true"
                            />
                            <span>{status}</span>
                          </span>
                          <span className="library-date-cell">
                            {date ? (
                              <time dateTime={document.created_at}>{date}</time>
                            ) : (
                              <span aria-label="Date unavailable">—</span>
                            )}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}

            {!documentsLoading &&
              workspaceDocuments.length > 0 &&
              visibleDocuments.length === 0 && (
                <div className="library-no-results" role="status">
                  <h2>
                  {search.trim() && statusFilter !== "all"
                    ? "No documents match your search and status filter."
                    : statusFilter !== "all"
                      ? "No documents match this status filter."
                      : "No documents match your search."}
                </h2>
                  <p>Try another file name.</p>
                </div>
              )}
          </section>
        )}
      </div>

      <style jsx>{`
        .document-library {
          min-height: 100%;
          color: var(--text-primary, #292a27);
        }

        .library-inner {
          width: 100%;
          margin: 0;
          padding: clamp(28px, 4vw, 54px) 0 48px;
        }

        .library-header {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 24px;
          padding-bottom: 25px;
          border-bottom: 1px solid var(--border, rgba(41, 42, 39, 0.15));
        }

        .library-heading {
          min-width: 0;
        }

        .library-empty-kicker {
          margin: 0 0 12px;
          color: var(--text-muted, #797a75);
          font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
          font-size: 10px;
          font-weight: 500;
          letter-spacing: 0.12em;
          line-height: 1.3;
          text-transform: uppercase;
        }

        .library-title-line {
          display: flex;
          align-items: baseline;
          flex-wrap: wrap;
          gap: 13px;
        }

        .library-title {
          margin: 0;
          font-size: clamp(42px, 5.5vw, 64px);
          font-weight: 400;
          letter-spacing: -0.045em;
          line-height: 0.98;
        }

        .library-count {
          padding-left: 13px;
          border-left: 1px solid var(--border-strong, rgba(41, 42, 39, 0.26));
          color: var(--text-secondary, #686963);
          font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
          font-size: 11px;
          line-height: 1.5;
        }

        .library-primary,
        .library-retry {
          display: inline-flex;
          flex: none;
          align-items: center;
          justify-content: center;
          gap: 8px;
          min-height: 40px;
          border: 1px solid transparent;
          border-radius: 7px;
          font: inherit;
          font-size: 13px;
          font-weight: 550;
          cursor: pointer;
          transition: background-color 140ms ease, border-color 140ms ease,
            color 140ms ease, transform 140ms ease;
        }

        .library-primary {
          padding: 0 15px;
          background: var(--accent, #a4412d);
          color: var(--accent-fg, #fff);
        }

        .library-primary:hover {
          filter: brightness(0.96);
        }

        .library-primary:active,
        .library-retry:active {
          transform: translateY(1px);
        }

        .library-primary:focus-visible,
        .library-retry:focus-visible,
        .library-row:focus-visible {
          outline: 2px solid var(--accent, #a4412d);
          outline-offset: 2px;
        }

        .library-browser {
          margin-top: 25px;
        }

        .library-toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 22px;
        }

        .library-search {
          width: min(100%, 390px);
        }

        .visually-hidden {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border: 0;
        }

        .library-search-control {
          display: flex;
          align-items: center;
          gap: 10px;
          min-height: 40px;
          padding: 0 11px;
          border: 1px solid var(--border, rgba(41, 42, 39, 0.15));
          border-radius: 7px;
          background: var(--bg-surface, #fff);
          color: var(--text-muted, #797a75);
          transition: border-color 140ms ease, box-shadow 140ms ease;
        }

        .library-search-control:focus-within {
          border-color: var(--accent, #a4412d);
          box-shadow: 0 0 0 2px var(--accent-primary-soft, rgba(164, 65, 45, 0.12));
        }

        .library-search-control svg {
          flex: none;
        }

        .library-search-control input {
          width: 100%;
          min-width: 0;
          padding: 0;
          border: 0;
          outline: 0;
          background: transparent;
          color: var(--text-primary, #292a27);
          font: inherit;
          font-size: 13px;
        }

        .library-search-control input::placeholder {
          color: var(--text-muted, #797a75);
          opacity: 0.82;
        }

        .library-refreshing,
        .library-loading {
          margin: 0;
          color: var(--text-secondary, #686963);
          font-size: 12px;
        }

        .library-loading {
          padding: 18px 10px;
          border-top: 1px solid var(--border, rgba(41, 42, 39, 0.15));
          border-bottom: 1px solid var(--border, rgba(41, 42, 39, 0.15));
        }

        .library-columns,
        .library-row {
          display: grid;
          grid-template-columns: minmax(0, 2.1fr) minmax(125px, 0.9fr) minmax(120px, 0.85fr) minmax(106px, 0.7fr);
          align-items: center;
          column-gap: 18px;
        }

        .library-columns {
          padding: 0 10px 10px;
          border-bottom: 1px solid var(--border-strong, rgba(41, 42, 39, 0.26));
          color: var(--text-muted, #797a75);
          font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
          font-size: 10px;
          letter-spacing: 0.09em;
          line-height: 1.3;
          text-transform: uppercase;
        }

        .library-rows {
          margin: 0;
          padding: 0;
          list-style: none;
        }

        .library-row-item {
          margin: 0;
          padding: 0;
        }

        .library-row {
          width: 100%;
          min-height: 58px;
          padding: 12px 10px;
          border: 0;
          border-bottom: 1px solid var(--border, rgba(41, 42, 39, 0.13));
          border-radius: 0;
          background: transparent;
          color: var(--text-primary, #292a27);
          font: inherit;
          text-align: left;
          cursor: pointer;
          transition: background-color 120ms ease;
        }

        .library-row:hover,
        .library-row[aria-pressed="true"] {
          background: var(--bg-secondary, #eeede8);
        }

        .library-file-cell {
          min-width: 0;
        }

        .library-file-name {
          display: block;
          overflow: hidden;
          font-size: 13px;
          font-weight: 550;
          line-height: 1.45;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .library-format-content {
          display: flex;
          min-width: 0;
          align-items: baseline;
          gap: 8px;
        }

        .library-format-kind {
          color: var(--text-primary, #292a27);
          font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
          font-size: 11px;
          letter-spacing: 0.025em;
        }

        .library-page-count {
          color: var(--text-secondary, #686963);
          font-size: 12px;
          white-space: nowrap;
        }

        .library-status-cell {
          display: flex;
          align-items: center;
          gap: 8px;
          color: var(--text-secondary, #686963);
          font-size: 12px;
          line-height: 1.4;
          white-space: nowrap;
        }

        .library-status-mark {
          width: 7px;
          height: 7px;
          flex: none;
          border-radius: 50%;
          background: var(--text-muted, #797a75);
        }

        .library-status-mark[data-status="ready"] {
          background: var(--success, #5b8063);
        }

        .library-status-mark[data-status="queued"] {
          background: var(--warning, #9b712c);
        }

        .library-status-mark[data-status="processing"] {
          background: var(--info, #55788b);
        }

        .library-status-mark[data-status="error"] {
          background: var(--error, #a4412d);
        }

        .library-date-cell {
          color: var(--text-secondary, #686963);
          font-size: 12px;
          line-height: 1.4;
          white-space: nowrap;
        }

        .library-mobile-label {
          display: none;
        }

        .library-error {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 18px;
          margin-top: 22px;
          padding: 13px 14px;
          border: 1px solid var(--border, rgba(41, 42, 39, 0.15));
          border-left: 3px solid var(--error, #a4412d);
          border-radius: 7px;
          background: var(--bg-surface, #fff);
        }

        .library-error-copy p {
          margin: 0;
          color: var(--text-secondary, #686963);
          font-size: 12px;
          line-height: 1.5;
          overflow-wrap: anywhere;
        }

        .library-error-copy .library-error-title {
          margin-bottom: 2px;
          color: var(--text-primary, #292a27);
          font-size: 13px;
          font-weight: 600;
        }

        .library-retry {
          min-height: 34px;
          padding: 0 10px;
          border-color: var(--border, rgba(41, 42, 39, 0.15));
          background: transparent;
          color: var(--text-primary, #292a27);
          font-size: 12px;
        }

        .library-retry:hover {
          background: var(--bg-secondary, #eeede8);
        }

        .library-empty {
          max-width: 680px;
          padding: clamp(42px, 7vw, 76px) 10px 48px;
        }

        .library-empty-kicker {
          margin-bottom: 12px;
        }

        .library-empty h2,
        .library-no-results h2 {
          margin: 0;
          font-family: var(--font-editorial, Georgia, serif);
          font-size: clamp(30px, 4vw, 42px);
          font-weight: 400;
          letter-spacing: -0.03em;
          line-height: 1.08;
        }

        .library-empty-description,
        .library-no-results p {
          max-width: 420px;
          margin: 12px 0 21px;
          color: var(--text-secondary, #686963);
          font-size: 14px;
          line-height: 1.6;
        }

        .library-no-results {
          padding: 36px 10px;
          border-bottom: 1px solid var(--border, rgba(41, 42, 39, 0.13));
        }

        .library-no-results h2 {
          font-size: 30px;
        }

        .library-no-results p {
          margin-bottom: 0;
        }

        @media (max-width: 760px) {
          .library-inner {
            padding: 30px 0 36px;
          }

          .library-header {
            align-items: flex-start;
          }

          .library-columns {
            display: none;
          }

          .library-row {
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 8px 14px;
            padding: 14px 9px;
          }

          .library-file-cell {
            grid-column: 1 / -1;
          }

          .library-file-name {
            overflow-wrap: anywhere;
            white-space: normal;
          }

          .library-format-cell {
            grid-column: 1;
          }

          .library-status-cell {
            grid-column: 2;
            justify-self: end;
          }

          .library-date-cell {
            grid-column: 1 / -1;
            font-size: 11px;
          }

          .library-mobile-label {
            display: inline;
            margin-right: 6px;
            color: var(--text-muted, #797a75);
            font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
            font-size: 9px;
            letter-spacing: 0.06em;
            text-transform: uppercase;
          }
        }

        @media (max-width: 540px) {
          .library-inner {
            padding-right: 0;
            padding-left: 0;
          }

          .library-header {
            flex-direction: column;
            gap: 18px;
          }

          .library-primary {
            min-height: 38px;
          }

          .library-toolbar {
            align-items: flex-start;
            flex-direction: column;
            margin-bottom: 15px;
          }

          .library-search {
            width: 100%;
          }

          .library-refreshing {
            font-size: 11px;
          }

          .library-error {
            align-items: flex-start;
            flex-direction: column;
          }
        }
      `}
        .library-toolbar {
          align-items: flex-end;
          flex-wrap: wrap;
        }

        .library-controls {
          display: flex;
          flex: 1 1 520px;
          align-items: flex-end;
          gap: 12px;
          min-width: 0;
        }

        .library-controls > .library-search {
          flex: 1 1 220px;
          min-width: 180px;
        }

        .library-filter-control {
          display: flex;
          flex: 0 0 auto;
          flex-direction: column;
          gap: 5px;
          min-width: 132px;
          color: var(--text-secondary, var(--text-primary, currentColor));
          font-size: 11px;
          line-height: 1.2;
        }

        .library-select {
          width: 100%;
          min-height: 40px;
          padding: 0 26px 0 10px;
          border: 1px solid var(--border-subtle, var(--text-primary, currentColor));
          border-radius: 6px;
          background: var(--bg-secondary, transparent);
          color: var(--text-primary, inherit);
          font: inherit;
          font-size: 12px;
          cursor: pointer;
        }

        .library-select:focus-visible,
        .library-clear-filters:focus-visible {
          outline: 2px solid var(--accent, currentColor);
          outline-offset: 2px;
        }

        .library-match-count {
          margin-left: auto;
          color: var(--text-secondary, var(--text-primary, currentColor));
          font-size: 12px;
          white-space: nowrap;
        }

        .library-clear-filters {
          border: 0;
          padding: 4px 0;
          background: transparent;
          color: var(--accent, var(--text-primary, currentColor));
          font: inherit;
          font-size: 12px;
          text-decoration: underline;
          text-underline-offset: 3px;
          cursor: pointer;
        }

        .library-format-kind {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .library-format-marker {
          display: inline-block;
          width: 7px;
          height: 9px;
          flex: 0 0 7px;
          box-sizing: border-box;
          border: 1px solid currentColor;
          border-radius: 1px;
          opacity: 0.65;
        }

        @media (max-width: 760px) {
          .library-controls {
            flex-wrap: wrap;
          }

          .library-controls > .library-search {
            flex-basis: 100%;
            min-width: 0;
          }

          .library-filter-control {
            flex: 1 1 132px;
          }
        }

        @media (max-width: 540px) {
          .library-match-count {
            margin-left: 0;
          }
        }

      </style>
    </section>
  );
}
