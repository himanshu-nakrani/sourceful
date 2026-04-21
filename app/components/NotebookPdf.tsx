"use client";

import { FileText, Loader2 } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface NotebookPdfProps {
  file: string;
  pageNumber: number;
  scale: number;
  onLoadSuccess: (payload: { numPages: number }) => void;
}

export function NotebookPdf({ file, pageNumber, scale, onLoadSuccess }: NotebookPdfProps) {
  return (
    <Document
      file={file}
      onLoadSuccess={onLoadSuccess}
      loading={
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
        </div>
      }
      error={
        <div className="flex h-full flex-col items-center justify-center text-gray-500">
          <FileText className="mb-4 h-16 w-16" />
          <p>Failed to load PDF</p>
        </div>
      }
    >
      <Page
        pageNumber={pageNumber}
        scale={scale}
        renderTextLayer
        renderAnnotationLayer
        className="shadow-xl"
      />
    </Document>
  );
}
