"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2, X, FileUp, Link as LinkIcon } from "lucide-react";
import { getJob, importWorkspaceUrl, ingestDocument, type JobInfo } from "../lib/api";
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";
import { EASE_OUT } from "../lib/motion";

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  initialFile?: File | null;
}

/**
 * Modal UI that lets the user select or drop a file, upload it for background indexing, poll job status until completion or error, refresh/select the resulting document, and then auto-close.
 *
 * The component validates provider settings before upload, shows queue/processing/done/error states (with job progress when available), prevents closing while submitting, and initializes the selected file from `initialFile` when the modal opens.
 *
 * @param open - Whether the modal is visible
 * @param onClose - Callback invoked to close the modal; will not be called while an upload is submitting
 * @param initialFile - Optional file to preselect when the modal becomes open
 * @returns The modal element when `open` is true, otherwise `null`
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
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && initialFile) {
      setFile(initialFile);
      setMode("file");
    }
  }, [open, initialFile]);

  const auth = {
    clientSessionId: settings.clientSessionId,
    providerApiKey: settings.providerApiKey,
  };

  const reset = () => {
    setFile(null);
    setUrlValue("");
    setUrlTitle("");
    setStatus("idle");
    setJob(null);
    setMessage("");
    setDragOver(false);
    setSubmitting(false);
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const pollJob = async (jobId: string, documentId: string) => {
    while (true) {
      const nextJob = await getJob(auth, jobId);
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
        window.setTimeout(handleClose, 1200);
        return;
      }
      if (nextJob.status === "error") {
        setMessage(nextJob.error_message || "Processing failed.");
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    if (!settings.providerApiKey.trim()) {
      setStatus("error");
      setMessage("Add your provider API key in Settings before uploading.");
      return;
    }

    setSubmitting(true);
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
      await refreshDocuments();
      if (response.status === "ready" || !response.job_id) {
        setStatus("done");
        setMessage(response.deduplicated ? "This document was already indexed." : "Document ready.");
        await selectDocument(response.document_id);
        window.setTimeout(handleClose, 1000);
        return;
      }
      setStatus("processing");
      await pollJob(response.job_id, response.document_id);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUrlImport = async () => {
    const trimmed = urlValue.trim();
    if (!trimmed) {
      setStatus("error");
      setMessage("URL is required.");
      return;
    }
    if (!activeWorkspaceId) {
      setStatus("error");
      setMessage("Select a workspace before importing a URL.");
      return;
    }
    if (!settings.providerApiKey.trim()) {
      setStatus("error");
      setMessage("Add your provider API key in Settings before importing URLs.");
      return;
    }
    setSubmitting(true);
    setStatus("queued");
    setMessage("");
    try {
      const source = await importWorkspaceUrl(auth, activeWorkspaceId, {
        url: trimmed,
        title: urlTitle.trim() || undefined,
        provider: settings.provider,
        embedding_model: settings.embeddingModel,
      });
      await refreshDocuments();
      if (source.status === "ready") {
        setStatus("done");
        setMessage("URL indexed and ready to chat.");
        if (source.document_id) {
          await selectDocument(source.document_id);
        }
        window.setTimeout(handleClose, 1200);
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
        window.setTimeout(handleClose, 1200);
      }
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "URL import failed.");
    } finally {
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

  const canSubmit =
    !submitting && (mode === "file" ? Boolean(file) : Boolean(urlValue.trim()) && Boolean(activeWorkspaceId));

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    const nextFile = event.dataTransfer.files[0];
    if (nextFile) setFile(nextFile);
  }, []);

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ background: "rgba(0, 0, 0, 0.5)", backdropFilter: "blur(8px)" }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={(event) => {
          if (event.target === event.currentTarget) handleClose();
        }}
      >
        {/* [a11y] Added role="dialog" and aria-modal for assistive technology support */}
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Upload document"
          className="rounded-2xl shadow-2xl overflow-hidden"
          style={{ width: "min(480px, 92vw)", background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
          initial={{ opacity: 0, scale: 0.95, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 8 }}
          transition={{ duration: 0.25, ease: EASE_OUT }}
        >
          <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
            <div>
              <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                Add a source
              </h2>
              <p className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                File or URL — queued for durable background indexing.
              </p>
            </div>
            <motion.button
              type="button"
              onClick={handleClose}
              className="p-1.5 rounded-xl"
              style={{ color: "var(--text-muted)" }}
              aria-label="Close modal"
              title="Close modal"
              whileHover={{ background: "var(--bg-surface)", color: "var(--text-secondary)" }}
              whileTap={{ scale: 0.9 }}
            >
              <X size={16} />
            </motion.button>
          </div>

          <div className="px-5 py-5">
            {/* Phase 1: file / URL mode tabs */}
            <div
              className="flex items-center gap-1 p-1 mb-4 rounded-xl"
              style={{ background: "var(--bg-tertiary)", border: "1px solid var(--border)" }}
            >
              {(["file", "url"] as const).map((m) => {
                const isActive = mode === m;
                return (
                  <button
                    key={m}
                    type="button"
                    onClick={() => {
                      if (submitting) return;
                      setMode(m);
                      setStatus("idle");
                      setMessage("");
                    }}
                    disabled={submitting}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
                    style={{
                      background: isActive ? "var(--bg-secondary)" : "transparent",
                      color: isActive ? "var(--text-primary)" : "var(--text-muted)",
                      border: isActive ? "1px solid var(--border-hover)" : "1px solid transparent",
                    }}
                  >
                    {m === "file" ? <FileUp size={12} /> : <LinkIcon size={12} />}
                    {m === "file" ? "Upload file" : "Import URL"}
                  </button>
                );
              })}
            </div>

            {mode === "url" ? (
              <div className="flex flex-col gap-3">
                {!activeWorkspaceId ? (
                  <div
                    className="rounded-xl px-3 py-2 text-xs"
                    style={{ background: "var(--warning-soft)", color: "var(--warning)" }}
                  >
                    Select a workspace before importing a URL.
                  </div>
                ) : null}
                <label className="flex flex-col gap-1">
                  <span
                    className="text-[10px] uppercase tracking-widest"
                    style={{ color: "var(--text-muted)" }}
                  >
                    URL
                  </span>
                  <input
                    value={urlValue}
                    onChange={(e) => setUrlValue(e.target.value)}
                    placeholder="https://example.com/article"
                    disabled={submitting}
                    className="rounded-lg px-3 py-2 text-sm outline-none"
                    style={{
                      background: "var(--bg-surface)",
                      color: "var(--text-primary)",
                      border: "1px solid var(--border)",
                    }}
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span
                    className="text-[10px] uppercase tracking-widest"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Title (optional)
                  </span>
                  <input
                    value={urlTitle}
                    onChange={(e) => setUrlTitle(e.target.value)}
                    placeholder="Defaults to page title"
                    disabled={submitting}
                    className="rounded-lg px-3 py-2 text-sm outline-none"
                    style={{
                      background: "var(--bg-surface)",
                      color: "var(--text-primary)",
                      border: "1px solid var(--border)",
                    }}
                  />
                </label>
                <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                  HTML pages and direct-PDF URLs are supported. Content larger than 10&nbsp;MB is rejected.
                </p>
              </div>
            ) : null}

            {/* [a11y] Added role, tabIndex, and onKeyDown for keyboard accessibility on drop zone */}
            {mode === "file" ? (
            <motion.div
              role="button"
              tabIndex={0}
              className="rounded-2xl cursor-pointer"
              style={{
                border: `2px dashed ${dragOver ? "var(--accent-brand)" : "var(--border-hover)"}`,
                background: dragOver ? "var(--accent-brand-soft)" : "var(--bg-tertiary)",
                padding: "2rem 1rem",
                textAlign: "center",
              }}
              onDragOver={(event) => {
                event.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              aria-label="Drop a file here or click to browse"
              whileHover={{ borderColor: "var(--accent-brand)" }}
              transition={{ duration: 0.15 }}
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
                <motion.div
                  className="flex flex-col items-center gap-2"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.2 }}
                >
                  <CheckCircle2 size={32} style={{ color: "var(--success)" }} />
                  <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    {file.name}
                  </p>
                  <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {(file.size / 1024).toFixed(0)} KB
                  </p>
                </motion.div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <motion.div
                    animate={{ y: [0, -3, 0] }}
                    transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                  >
                    <FileUp size={32} style={{ color: "var(--text-muted)" }} />
                  </motion.div>
                  <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
                    Drop a file here or click to browse
                  </p>
                  <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    PDF, TXT, MD, DOCX, CSV
                  </p>
                </div>
              )}
            </motion.div>
            ) : null}

            <AnimatePresence>
              {status !== "idle" ? (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-4 rounded-2xl px-4 py-3 overflow-hidden"
                  style={{
                    background:
                      status === "error"
                        ? "var(--error-soft)"
                        : status === "done"
                        ? "var(--success-soft)"
                        : "var(--accent-brand-soft)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex items-center gap-2">
                    {status === "done" ? (
                      <CheckCircle2 size={14} style={{ color: "var(--success)" }} />
                    ) : status === "error" ? (
                      <X size={14} style={{ color: "var(--error)" }} />
                    ) : (
                      <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent-brand)" }} />
                    )}
                    <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {status === "queued" && "Queued for processing"}
                      {status === "processing" && (job?.stage ? `Processing: ${job.stage}` : "Processing")}
                      {status === "done" && "Done"}
                      {status === "error" && "Error"}
                    </span>
                  </div>
                  {job ? (
                    <>
                      <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                        <motion.div
                          className="h-full rounded-full"
                          style={{
                            background: status === "done" ? "var(--success)" : "var(--gradient-accent)",
                          }}
                          initial={{ width: "8%" }}
                          animate={{ width: `${Math.max(8, Math.round((job.progress || 0) * 100))}%` }}
                          transition={{ duration: 0.5, ease: "easeOut" }}
                        />
                      </div>
                      <p className="mt-2 text-[11px]" style={{ color: "var(--text-muted)" }}>
                        Attempt {job.attempt_count} of {job.max_attempts}
                        {job.next_retry_at ? ` · next retry ${new Date(job.next_retry_at).toLocaleTimeString()}` : ""}
                        {job.terminal ? " · terminal failure" : ""}
                      </p>
                    </>
                  ) : null}
                  {message ? (
                    <p className="mt-2 text-xs" style={{ color: status === "error" ? "var(--error)" : "var(--text-secondary)" }}>
                      {message}
                    </p>
                  ) : null}
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>

          <div className="flex items-center justify-end gap-2 px-5 py-4" style={{ borderTop: "1px solid var(--border)" }}>
            <motion.button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 rounded-xl text-sm"
              style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
              whileHover={{ borderColor: "var(--border-hover)" }}
              whileTap={{ scale: 0.97 }}
            >
              Cancel
            </motion.button>
            <motion.button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="px-5 py-2 rounded-xl text-sm font-semibold"
              style={{
                background: !canSubmit ? "var(--bg-elevated)" : "var(--gradient-accent)",
                color: !canSubmit ? "var(--text-muted)" : "#fff",
                boxShadow: canSubmit ? "var(--shadow-glow-teal)" : "none",
              }}
              whileHover={canSubmit ? { scale: 1.02 } : {}}
              whileTap={canSubmit ? { scale: 0.97 } : {}}
              transition={{ type: "spring", stiffness: 400, damping: 17 }}
            >
              {submitting ? "Working…" : mode === "file" ? "Upload" : "Import URL"}
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
