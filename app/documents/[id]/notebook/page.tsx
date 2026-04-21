"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { NotebookView } from "../../../components/NotebookView";
import { StoreProvider } from "../../../lib/store";

interface NotebookPageProps {
  params: Promise<{ id: string }>;
}

function NotebookPageContent({ documentId }: { documentId: string }) {
  const router = useRouter();
  return <NotebookView documentId={documentId} onClose={() => router.push("/dashboard")} />;
}

export default function NotebookPage({ params }: NotebookPageProps) {
  const { id } = use(params);

  return (
    <StoreProvider>
      <NotebookPageContent documentId={id} />
    </StoreProvider>
  );
}
