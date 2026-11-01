import type { Metadata } from "next";

import NotebookClient from "./NotebookClient";

interface NotebookPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ page?: string | string[] }>;
}

export async function generateMetadata({ params }: NotebookPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: "Notebook",
    description: `Read and query document ${id} side by side in the Sourceful notebook.`,
  };
}

/**
 * Server shell for the notebook route: carries route metadata and mounts the
 * client notebook viewer.
 */
export default async function NotebookPage({ params, searchParams }: NotebookPageProps) {
  const query = await searchParams;
  const page = Number(Array.isArray(query.page) ? query.page[0] : query.page);
  const initialPage = Number.isSafeInteger(page) && page > 0 ? page : 1;
  return <NotebookClient params={params} initialPage={initialPage} />;
}
