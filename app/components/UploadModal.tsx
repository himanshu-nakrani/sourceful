"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FileUp, Link as LinkIcon, X } from "lucide-react";
import { getJob, importWorkspaceUrl, ingestDocument, type JobInfo } from "../lib/api";
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";
import { transitionNormal } from "../lib/motion";
import { Button, ErrorBanner, Modal, StatusDot, TextField } from "./ui";

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  initialFile?: File | null;
}

/**
 * Modal UI that lets the user select or drop a file (or import a URL), submit
 * it for background indexing, poll job status until completion or error,
 * refresh/select the resulting document, and then auto-close.
 *
 * The component validates provider settings before upload, shows
 * queued/processing/done/error states (with job progress, attempt counts, and
 * retry timing when available). Closing is blocked only while a submission
 * request is actually in flight; during background polling the modal stays
 * closable and closing simply stops watching the job (the server-side job
 * keeps running and the document list's polling picks up the result).
 *
 * @param open - Whether the modal is visible
 * @param onClose - Callback invoked to close the modal; never called while a submission request is in flight
 * @param initialFile - Optional file to preselect when the modal becomes open
 * @returns The modal element
 */
export default function UploadModal({ open, onClose, initialFile }: UploadModalProps) {
  const { state } = useStore();
  const { refreshDocuments, selectDocument } = useServerState();
  const { settings, activeWorkspaceId } = state;
  const [mode, setMode] = useState<"file" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [urlValue, setUrlValue] = useState("");
  const [urlTitle, setUrlTitle] = useState("");
  const [status, setStatus] = useState<"idle" | "queued" | "processing" | "done" | "error">("idle");
  const [job, setJob] = useState<JobInfo | null>(null);
  const [message, setMessage] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [zoneHover, setZoneHover] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [retryable, setRetryable] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const submittingRef = useRef(false);

  // Fix #11: track the active polling session so a stale pollJob loop exits
  // when the modal is closed and quickly reopened. A boolean "cancelled" ref
  // would be reset to false on reopen and let an in-flight loop resume,
  // spawning concurrent loops that clobber each other's state.
  //
  // Two refs, because session ids must be single-use: `pollSeqRef` only ever
  // increments and hands out a fresh id per open, while `pollSessionRef` holds
  // the currently-active id (0 = nothing polling). Cancelling writes 0 rather
  // than reusing a low id, so an abandoned loop can never be handed its own id
  // back on a later open and revived.
  const pollSeqRef = useRef(0);
  const pollSessionRef = useRef(0);

  // [Fix 6.7.2] Auto-close timer id, so the pending close can be cancelled on
  // unmount and on manual close.
  const autoCloseTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (open) {
      pollSessionRef.current = ++pollSeqRef.current;
    }
  }, [open]);

  // Clean up on unmount: cancel polling and any pending auto-close.
  useEffect(() => {
    return () => {
      pollSessionRef.current = 0;
      clearAutoCloseTimer();
    };
  }, []);

  useEffect(() => {
    if (open && initialFile) {
      setFile(initialFile);
      setMode("file");
    }
  }, [open, initialFile]);

  // [Fix 5.4] Stable auth identity built from its primitive parts so consumers
  // don't see a new object on every render.
  const auth = useMemo(
    () => ({ clientSessionId: settings.clientSessionId, providerApiKey: settings.providerApiKey }),
    [settings.clientSessionId, settings.providerApiKey],
  );

  const clearAutoCloseTimer = () => {
    if (autoCloseTimerRef.current !== null) {
      window.clearTimeout(autoCloseTimerRef.current);
      autoCloseTimerRef.current = null;
    }
  };

  const scheduleAutoClose = (delay: number) => {
    clearAutoCloseTimer();
    autoCloseTimerRef.current = window.setTimeout(() => handleClose(), delay);
  };

  const reset = () => {
    setFile(null);
    setUrlValue("");
    setUrlTitle("");
    setStatus("idle");
    setJob(null);
    setMessage("");
    setDragOver(false);
    submittingRef.current = false;
    setSubmitting(false);
    setRetryable(false);
  };

  const handleClose = () => {
    if (submittingRef.current) return;
    // [Fix 6.7.2] Closing during background polling cancels the poll loop and
    // any pending auto-close; the server-side job keeps running and the
    // document list's polling picks up the result. 0 means "nothing active" and
    // is never handed out as a session id, so this loop cannot be revived.
    pollSessionRef.current = 0;
    clearAutoCloseTimer();
    reset();
    onClose();
  };

  const pollJob = async (jobId: string, documentId: string) => {
    const session = pollSessionRef.current;
    const isActive = () => session !== 0 && session === pollSessionRef.current;
    while (isActive()) {
      const nextJob = await getJob(auth, jobId);
      if (!isActive()) return;
      setJob(nextJob);
      setStatus(
        nextJob.status === "ready"
          ? "done"
          : nextJob.status === "error"
            ? "error"
            : nextJob.status === "queued"
              ? "queued"
              : "processing"
      );
      if (nextJob.status === "ready") {
        await refreshDocuments();
        await selectDocument(documentId);
        setMessage("Document indexed and ready to chat.");
        scheduleAutoClose(1200);
        return;
      }
      if (nextJob.status === "error") {
        setMessage(nextJob.error_message || "Processing failed.");
        setRetryable(true);
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }
  };

  const handleUpload = async () => {
    if (!file || submittingRef.current) return;
    if (!settings.providerApiKey.trim()) {
      setStatus("error");
      setMessage("Add your provider API key in Settings before uploading.");
      setRetryable(false);
      return;
    }

    submittingRef.current = true;
    setSubmitting(true);
    setRetryable(false);
    setStatus("queued");
    setMessage("");
    try {
      const response = await ingestDocument(
        auth,
        settings.provider,
        file,
        settings.embeddingModel,
        activeWorkspaceId ?? undefined
      );
      // Only the submission request blocks closing; polling stays cancellable.
      submittingRef.current = false;
      setSubmitting(false);
      await refreshDocuments();
      if (response.status === "ready" || !response.job_id) {
        setStatus("done");
        setMessage(response.deduplicated ? "This document was already indexed." : "Document ready.");
        await selectDocument(response.document_id);
        scheduleAutoClose(1000);
        return;
      }
      setStatus("processing");
      await pollJob(response.job_id, response.document_id);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Upload failed.");
      setRetryable(true);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const handleUrlImport = async () => {
    if (submittingRef.current) return;
    const trimmed = urlValue.trim();
    if (!trimmed) {
      setStatus("error");
      setMessage("URL is required.");
      setRetryable(false);
      return;
    }
    if (!activeWorkspaceId) {
      setStatus("error");
      setMessage("Select a workspace before importing a URL.");
      setRetryable(false);
      return;
    }
    if (!settings.providerApiKey.trim()) {
      setStatus("error");
      setMessage("Add your provider API key in Settings before importing URLs.");
      setRetryable(false);
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setRetryable(false);
    setStatus("queued");
    setMessage("");
    try {
      const source = await importWorkspaceUrl(auth, activeWorkspaceId, {
        url: trimmed,
        title: urlTitle.trim() || undefined,
        provider: settings.provider,
        embedding_model: settings.embeddingModel,
      });
      submittingRef.current = false;
      setSubmitting(false);
      await refreshDocuments();
      if (source.status === "ready") {
        setStatus("done");
        setMessage("URL indexed and ready to chat.");
        if (source.document_id) {
          await selectDocument(source.document_id);
        }
        scheduleAutoClose(1200);
        return;
      }
      const jobId =
        (source.metadata && typeof source.metadata["job_id"] === "string"
          ? (source.metadata["job_id"] as string)
          : null) ?? null;
      if (jobId && source.document_id) {
        setStatus("processing");
        await pollJob(jobId, source.document_id);
      } else {
        setStatus("done");
        setMessage("URL queued for indexing.");
        scheduleAutoClose(1200);
      }
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "URL import failed.");
      setRetryable(true);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const handleSubmit = () => {
    if (mode === "file") {
      void handleUpload();
    } else {
      void handleUrlImport();
    }
  };

  // The form stays frozen for the whole active flow (request + background
  // polling) so a job can't be double-submitted, even though closing is
  // allowed during polling [Fix 6.7.2].
  const flowActive = submitting || status === "queued" || status === "processing";
  const canSubmit =
    !flowActive && (mode === "file" ? Boolean(file) : Boolean(urlValue.trim()) && Boolean(activeWorkspaceId));

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    const nextFile = event.dataTransfer.files[0];
    if (nextFile) setFile(nextFile);
  }, []);

  const progressPct = job
    ? Math.min(100, Math.max(8, Math.round((job.progress || 0) * 100)))
    : 0;

  const fileTone =
    status === "done"
      ? "success"
      : status === "error"
        ? "error"
        : status === "queued" || status === "processing"
          ? "processing"
          : "idle";

  const statusLabel =
    status === "queued"
      ? "Queued for processing"
      : status === "processing"
        ? job?.stage
          ? `Processing: ${job.stage}`
          : "Processing"
        : "Done";

  const zoneActive = dragOver || zoneHover;

  return (
    <Modal
      open={open}
      onClose={handleClose}
      busy={submitting}
      title="Add a source"
      width={480}
      className="flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div
        className="flex items-start justify-between gap-4 px-5 py-4 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <h2 className="display text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Add a source
          </h2>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-tertiary)" }}>
            File or URL — queued for durable background indexing.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClose}
          aria-label="Close modal"
          title="Close modal"
        >
          <X size={14} />
        </Button>
      </div>

      {/* Body */}
      <div className="px-5 py-4 flex flex-col gap-4">
        {/* File / URL mode tabs */}
        <div
          className="flex items-center gap-1 p-1 rounded-lg"
          style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border)" }}
        >
          {(["file", "url"] as const).map((tabMode) => {
            const isActive = mode === tabMode;
            return (
              <button
                key={tabMode}
                type="button"
                onClick={() => {
                  if (flowActive) return;
                  setMode(tabMode);
                  setStatus("idle");
                  setMessage("");
                }}
                disabled={flowActive}
                aria-pressed={isActive}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus-ring disabled:cursor-not-allowed"
                style={{
                  background: isActive ? "var(--bg-surface)" : "transparent",
                  color: isActive ? "var(--text-primary)" : "var(--text-muted)",
                  border: `1px solid ${isActive ? "var(--border-hover)" : "transparent"}`,
                }}
              >
                {tabMode === "file" ? <FileUp size={12} /> : <LinkIcon size={12} />}
                {tabMode === "file" ? "Upload file" : "Import URL"}
              </button>
            );
          })}
        </div>

        {mode === "url" ? (
          <div className="flex flex-col gap-3">
            {!activeWorkspaceId ? (
              <div
                className="rounded-lg px-3 py-2 text-xs"
                style={{ background: "var(--warning-soft)", color: "var(--warning)" }}
              >
                Select a workspace before importing a URL.
              </div>
            ) : null}
            <TextField
              label="URL"
              type="url"
              value={urlValue}
              onChange={(event) => setUrlValue(event.target.value)}
              placeholder="https://example.com/article"
              disabled={flowActive}
            />
            <TextField
              label="Title (optional)"
              value={urlTitle}
              onChange={(event) => setUrlTitle(event.target.value)}
              placeholder="Defaults to page title"
              disabled={flowActive}
            />
            <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
              Imports into your active workspace. HTML pages and direct-PDF URLs are
              supported; content larger than 10&nbsp;MB is rejected.
            </p>
          </div>
        ) : (
          <div
            role="button"
            tabIndex={0}
            className="rounded-xl cursor-pointer"
            style={{
              border: `1px dashed ${zoneActive ? "var(--accent-primary)" : "var(--border)"}`,
              background: zoneActive ? "var(--accent-primary-soft)" : "var(--bg-tertiary)",
              padding: "2rem 1rem",
              textAlign: "center",
              transition: "border-color 0.15s ease, background 0.15s ease",
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onMouseEnter={() => setZoneHover(true)}
            onMouseLeave={() => setZoneHover(false)}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            aria-label="Drop a file here or click to browse"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md,.docx,.csv"
              className="hidden"
              onChange={(event) => {
                const nextFile = event.target.files?.[0];
                if (nextFile) setFile(nextFile);
              }}
            />
            {file ? (
              <div className="flex flex-col items-center gap-2.5">
                <div
                  className="flex items-center gap-2.5 rounded-lg px-3 py-2.5 max-w-full text-left"
                  style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
                >
                  <StatusDot tone={fileTone} pulse={fileTone === "processing"} />
                  <span className="min-w-0">
                    <span
                      className="block truncate text-[13px] font-medium"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {file.name}
                    </span>
                    <span className="block data-num text-xs" style={{ color: "var(--text-tertiary)" }}>
                      {file.size < 1024
                        ? `${Math.max(0.1, Math.round(file.size / 100) / 10)} KB`
                        : `${Math.round(file.size / 1024)} KB`}
                    </span>
                  </span>
                </div>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Click to choose a different file
                </p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <FileUp size={28} style={{ color: "var(--text-muted)" }} />
                <p className="text-[13px] font-medium" style={{ color: "var(--text-secondary)" }}>
                  Drop a file here or click to browse
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  PDF, TXT, MD, DOCX, CSV
                </p>
              </div>
            )}
          </div>
        )}

        {/* Status strip */}
        <AnimatePresence initial={false}>
          {status !== "idle" ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={transitionNormal}
              className="overflow-hidden"
            >
              {status === "error" ? (
                <ErrorBanner
                  message={message || "Something went wrong."}
                  onRetry={retryable ? handleSubmit : undefined}
                />
              ) : (
                <div
                  className="rounded-lg px-3.5 py-3 flex flex-col gap-2"
                  style={{
                    background: status === "done" ? "var(--success-soft)" : "var(--bg-tertiary)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <StatusDot
                      tone={status === "done" ? "success" : "processing"}
                      pulse={status !== "done"}
                      label={statusLabel}
                    />
                    {job ? (
                      <span className="data-num text-xs" style={{ color: "var(--text-secondary)" }}>
                        {progressPct}%
                      </span>
                    ) : null}
                  </div>
                  {job ? (
                    <div
                      className="h-1 rounded-full overflow-hidden"
                      style={{ background: "var(--bg-highest)" }}
                    >
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${progressPct}%`,
                          background: status === "done" ? "var(--success)" : "var(--accent-primary)",
                          transition: "width 0.3s ease",
                        }}
                      />
                    </div>
                  ) : null}
                  {job ? (
                    <p className="data-num text-xs" style={{ color: "var(--text-tertiary)" }}>
                      Attempt {job.attempt_count} of {job.max_attempts}
                      {job.next_retry_at
                        ? ` · next retry ${new Date(job.next_retry_at).toLocaleTimeString()}`
                        : ""}
                      {job.terminal ? " · terminal failure" : ""}
                    </p>
                  ) : null}
                  {message ? (
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      {message}
                    </p>
                  ) : null}
                </div>
              )}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-end gap-2 px-5 py-4 shrink-0"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Button variant="secondary" onClick={handleClose}>
          Cancel
        </Button>
        <Button variant="primary" onClick={handleSubmit} disabled={!canSubmit}>
          {submitting ? "Working…" : mode === "file" ? "Upload" : "Import URL"}
        </Button>
      </div>
    </Modal>
  );
}
