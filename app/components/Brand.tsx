import { Layers2 } from "lucide-react";

export default function Brand({ className = "" }: { className?: string }) {
  return (
    <div className={`inline-flex items-center gap-2.5 ${className}`} aria-label="Sourceful">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
        style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
      >
        <Layers2 size={20} strokeWidth={1.8} aria-hidden="true" />
      </span>
      <span className="text-[22px] font-semibold tracking-[-0.055em]" style={{ color: "var(--text-primary)" }}>
        sourceful<span style={{ color: "var(--accent-primary)" }}>.</span>
      </span>
    </div>
  );
}
