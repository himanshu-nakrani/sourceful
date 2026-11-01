export default function Brand({ className = "" }: { className?: string }) {
  return (
    <div className={`inline-flex items-center gap-2.5 ${className}`} aria-label="Sourceful">
      <svg width="23" height="28" viewBox="0 0 23 28" fill="none" aria-hidden="true" className="shrink-0" style={{ color: "var(--text-primary)" }}>
        <path d="M7 4H3V24H7M16 4H20V24H16" stroke="currentColor" strokeWidth="1.6" />
        <path d="M9 10H14M9 14H14M9 18H12" stroke="var(--accent-primary)" strokeWidth="1.6" />
      </svg>
      <span className="editorial-heading text-[29px] leading-none" style={{ color: "var(--text-primary)" }}>sourceful</span>
    </div>
  );
}
