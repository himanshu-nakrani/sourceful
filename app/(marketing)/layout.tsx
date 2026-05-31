import "./marketing.css";

export const metadata = {
  title: "Sourceful — AI-Powered Document Intelligence",
  description: "Enterprise-grade RAG platform with advanced retrieval, multi-modal ingestion, and agentic capabilities.",
};

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="marketing min-h-screen">
      {children}
    </div>
  );
}
