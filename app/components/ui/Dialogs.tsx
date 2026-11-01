"use client";

import React, { useEffect, useRef, useState } from "react";

import { Button } from "./Button";
import { Modal } from "./Modal";
import { TextField } from "./Field";

/**
 * Confirmation dialog replacing window.confirm. `busy` keeps the dialog
 * open (and buttons disabled) while the caller's promise is in flight.
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} onClose={onCancel} busy={busy} title={title} width={400}>
      <div className="p-5">
        <h2 className="text-[15px] font-semibold mb-1.5" style={{ color: "var(--text-primary)" }}>
          {title}
        </h2>
        <p className="text-[13px] leading-relaxed mb-5" style={{ color: "var(--text-secondary)" }}>
          {message}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "primary"} size="sm" onClick={onConfirm} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/**
 * Single-line input dialog replacing window.prompt. Enter submits, Escape
 * cancels, and the input starts focused and selected. The form is keyed by
 * the open request so state initializes from props on each open.
 */
export function PromptDialog({
  open,
  title,
  label,
  initialValue = "",
  placeholder,
  submitLabel = "Save",
  busy = false,
  onSubmit,
  onCancel,
}: {
  open: boolean;
  title: string;
  label: string;
  initialValue?: string;
  placeholder?: string;
  submitLabel?: string;
  busy?: boolean;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} onClose={onCancel} busy={busy} title={title} width={400}>
      {open ? (
        <PromptForm
          key={initialValue}
          title={title}
          label={label}
          initialValue={initialValue}
          placeholder={placeholder}
          submitLabel={submitLabel}
          busy={busy}
          onSubmit={onSubmit}
          onCancel={onCancel}
        />
      ) : null}
    </Modal>
  );
}

function PromptForm({
  title,
  label,
  initialValue,
  placeholder,
  submitLabel,
  busy,
  onSubmit,
  onCancel,
}: {
  title: string;
  label: string;
  initialValue: string;
  placeholder?: string;
  submitLabel: string;
  busy: boolean;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);

  // Select the text once the modal has focused the input (DOM only).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const input = inputRef.current;
      if (input && document.activeElement === input) input.select();
    }, 60);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <form
      className="p-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (value.trim() && !busy) onSubmit(value.trim());
      }}
    >
      <h2 className="text-[15px] font-semibold mb-3.5" style={{ color: "var(--text-primary)" }}>
        {title}
      </h2>
      <TextField
        ref={inputRef}
        label={label}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setValue(event.target.value)}
      />
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="ghost" size="sm" type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" type="submit" disabled={busy || !value.trim()}>
          {busy ? "Working…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
