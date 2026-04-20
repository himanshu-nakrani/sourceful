"use client";

import React from "react";
import NotebookView from "../../../components/NotebookView";

export default function NotebookPage({ params }: { params: { id: string } }) {
  return <NotebookView documentId={params.id} />;
}
