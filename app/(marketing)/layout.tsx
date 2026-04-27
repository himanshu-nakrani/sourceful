export const metadata = {
  title: "DocRAG - Traceable Document Intelligence",
  description: "Self-hostable document QA workspace with cited retrieval, source review, and workspace controls.",
};

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className="min-h-screen"
      style={{
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
      }}
    >
      {children}
    </div>
  );
}
