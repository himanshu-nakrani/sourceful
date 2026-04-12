import type { Metadata } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Document RAG — AI-Powered Document Q&A",
  description:
    "Upload PDFs, DOCX, and text files, index them with embeddings, then ask questions with AI-powered retrieval-augmented generation. Supports OpenAI and Google Gemini.",
  keywords: ["RAG", "document QA", "AI", "embeddings", "OpenAI", "Gemini", "PDF"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} h-full`}
    >
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
