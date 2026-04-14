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

/**
 * Root HTML layout that applies global fonts, viewport settings, and a pre-paint theme selection.
 *
 * Injects a viewport meta tag and an inline script that reads `localStorage.getItem('rag-prefs')`
 * and sets `document.documentElement`'s `data-theme` attribute to `"light"` before the first paint when the saved theme is `"light"`.
 *
 * @param children - The page content to render inside the document body
 * @returns The root HTML element containing the configured head and body with the provided `children`
 */
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
        {/* Apply theme before first paint to prevent flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var p=localStorage.getItem('rag-prefs');if(p){var t=JSON.parse(p).theme;if(t==='light')document.documentElement.setAttribute('data-theme','light');}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
