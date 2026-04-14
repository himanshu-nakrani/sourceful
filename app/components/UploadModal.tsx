"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Upload, X } from "lucide-react";
import { getJob, ingestDocument, type JobInfo } from "../lib/api";
import { useServerState } from "../lib/server-state";
import { useStore } from "../lib/store";

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
  const { settings } = state;
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "queued" | "processing" | "done" | "error">("idle");
  const [job, setJob] = useState<JobInfo | null>(null);
  const [message, setMessage] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && initialFile) {
      setFile(initialFile);
    }
  }, [open, initialFile]);

  const auth = {
    clientSessionId: settings.clientSessionId,
    providerApiKey: settings.providerApiKey,
  };

  const reset = () => {
    setFile(null);
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
      const response = await ingestDocument(auth, settings.provider, file, settings.embeddingModel);
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

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setDragOver(false);
    const nextFile = event.dataTransfer.files[0];
    if (nextFile) setFile(nextFile);
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in"
      style={{ background: "rgba(0, 0, 0, 0.6)", backdropFilter: "blur(4px)" }}
      onClick={(event) => {
        if (event.target === event.currentTarget) handleClose();
      }}
    >
      {/* [a11y] Added role="dialog" and aria-modal for assistive technology support */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Upload document"
        className="rounded-2xl shadow-2xl animate-scale-in"
        style={{ width: "min(520px, 92vw)", background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
          <div>
            <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
              Upload Document
            </h2>
            <p className="text-xs mt-1" style={{ color: "var(--text-tertiary)" }}>
              Files are queued for durable background indexing.
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded-md"
            style={{ color: "var(--text-tertiary)" }}
            aria-label="Close modal"
            title="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-5">
          {/* [a11y] Added role, tabIndex, and onKeyDown for keyboard accessibility on drop zone */}
          <div
            role="button"
            tabIndex={0}
            className="rounded-xl transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
            style={{
              border: `2px dashed ${dragOver ? "var(--accent)" : "var(--border-hover)"}`,
              background: dragOver ? "var(--accent-soft)" : "var(--bg-tertiary)",
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
              <div className="flex flex-col items-center gap-2">
                <CheckCircle2 size={36} style={{ color: "var(--success)" }} />
                <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  {file.name}
                </p>
                <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                  {(file.size / 1024).toFixed(0)} KB
                </p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Upload size={36} style={{ color: "var(--text-muted)" }} />
                <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
                  Drop a file here or click to browse
                </p>
                <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                  PDF, TXT, MD, DOCX, CSV · UTF-8 required for text files
                </p>
              </div>
            )}
          </div>

          {status !== "idle" ? (
            <div
              className="mt-4 rounded-xl px-4 py-3"
              style={{
                background:
                  status === "error"
                    ? "var(--error-soft)"
                    : status === "done"
                    ? "var(--success-soft)"
                    : "var(--accent-soft)",
                border: "1px solid var(--border)",
              }}
            >
              <div className="flex items-center gap-2">
                {status === "done" ? (
                  <CheckCircle2 size={16} style={{ color: "var(--success)" }} />
                ) : status === "error" ? (
                  <X size={16} style={{ color: "var(--error)" }} />
                ) : (
                  <Loader2 size={16} className="animate-spin" style={{ color: "var(--accent)" }} />
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
                  <div className="mt-3 h-2 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.max(8, Math.round((job.progress || 0) * 100))}%`,
                        background: status === "done" ? "var(--success)" : "var(--accent)",
                      }}
                    />
                  </div>
                  <p className="mt-2 text-xs" style={{ color: "var(--text-tertiary)" }}>
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
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4" style={{ borderTop: "1px solid var(--border)" }}>
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 rounded-lg text-sm"
            style={{ background: "var(--bg-surface)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!file || submitting}
            className="px-5 py-2 rounded-lg text-sm font-medium"
            style={{
              background: !file || submitting ? "var(--bg-elevated)" : "var(--accent)",
              color: !file || submitting ? "var(--text-tertiary)" : "var(--accent-fg)",
            }}
          >
            {submitting ? "Working…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
