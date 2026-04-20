export const metadata = {
  title: "Document QA - AI-Powered Document Intelligence",
  description: "Enterprise-grade RAG platform with advanced retrieval, multi-modal ingestion, and agentic capabilities.",
};

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-white dark:bg-gray-900">
      {children}
    </div>
  );
}
