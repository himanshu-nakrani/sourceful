"use client";

import React from "react";

/**
 * Labeled text input on the Signal token system.
 */
export const TextField = React.forwardRef<
  HTMLInputElement,
  {
    label: string;
    hint?: string;
    error?: string | null;
    mono?: boolean;
    required?: boolean;
  } & React.InputHTMLAttributes<HTMLInputElement>
>(function TextField(
  { label, hint, error, mono = false, required = false, className = "", style, ...rest },
  ref,
) {
  const id = React.useId();
  const describedById = `${id}-desc`;
  return (
    <div className={className} style={style}>
      <label htmlFor={id} className="block text-[13px] mb-1.5" style={{ color: "var(--text-secondary)" }}>
        {label}
        {required && (
          <span style={{ color: "var(--error)", marginLeft: "0.25rem" }} aria-hidden="true">
            *
          </span>
        )}
      </label>
      <input
        ref={ref}
        id={id}
        required={required}
        className="w-full rounded-lg px-3.5 py-2.5 text-sm outline-none focus-ring transition-all"
        style={{
          background: "var(--bg-surface)",
          border: `1px solid ${error ? "var(--error)" : "var(--border)"}`,
          color: "var(--text-primary)",
          fontFamily: mono ? "var(--font-mono), monospace" : undefined,
        }}
        aria-invalid={error ? true : undefined}
        // Associate whichever of error/hint is rendered, so screen readers
        // announce it with the field instead of leaving it orphaned.
        aria-describedby={error || hint ? describedById : undefined}
        {...rest}
      />
      {error ? (
        <p id={describedById} className="mt-1.5 text-xs" style={{ color: "var(--error)" }} role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={describedById} className="mt-1.5 text-xs" style={{ color: "var(--text-tertiary)" }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
});

/**
 * Labeled select dropdown.
 */
export function SelectField({
  label,
  hint,
  options,
  className = "",
  style,
  ...rest
}: {
  label: string;
  hint?: string;
  options: { value: string; label: string }[];
} & React.SelectHTMLAttributes<HTMLSelectElement>) {
  const id = React.useId();
  const hintId = `${id}-desc`;
  return (
    <div className={className} style={style}>
      <label htmlFor={id} className="block text-[13px] mb-1.5" style={{ color: "var(--text-secondary)" }}>
        {label}
      </label>
      <select
        id={id}
        className="w-full rounded-lg px-3 py-2.5 text-sm outline-none focus-ring transition-all appearance-none cursor-pointer"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
        }}
        aria-describedby={hint ? hintId : undefined}
        {...rest}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} style={{ background: "var(--bg-secondary)" }}>
            {opt.label}
          </option>
        ))}
      </select>
      {hint ? (
        <p id={hintId} className="mt-1.5 text-xs" style={{ color: "var(--text-tertiary)" }}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Labeled range slider with a mono value readout.
 */
export function SliderField({
  label,
  value,
  format,
  className = "",
  style,
  ...rest
}: {
  label: string;
  value: number;
  format?: (value: number) => string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "type">) {
  const id = React.useId();
  return (
    <div className={className} style={style}>
      <div className="flex items-center justify-between mb-1.5">
        <label htmlFor={id} className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
          {label}
        </label>
        <span className="data-num text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--bg-surface)", color: "var(--text-secondary)" }}>
          {format ? format(value) : value}
        </span>
      </div>
      <input
        id={id}
        type="range"
        value={value}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer focus-ring"
        style={{ background: "var(--bg-highest)", accentColor: "var(--accent-primary)" }}
        {...rest}
      />
    </div>
  );
}

/**
 * Toggle switch with an accessible description.
 */
export function ToggleField({
  label,
  description,
  checked,
  onCheckedChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className="w-full flex items-center justify-between gap-4 rounded-lg px-3 py-2.5 text-left transition-colors focus-ring"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
    >
      <span className="flex flex-col gap-0.5">
        <span className="text-[13px]" style={{ color: "var(--text-primary)" }}>
          {label}
        </span>
        {description ? (
          <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
            {description}
          </span>
        ) : null}
      </span>
      <span
        aria-hidden="true"
        className="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors"
        style={{ background: checked ? "var(--accent-primary)" : "var(--bg-highest)" }}
      >
        <span
          className="absolute h-3.5 w-3.5 rounded-full transition-transform"
          style={{
            background: checked ? "var(--accent-fg)" : "var(--text-tertiary)",
            transform: checked ? "translateX(20px)" : "translateX(4px)",
          }}
        />
      </span>
    </button>
  );
}
