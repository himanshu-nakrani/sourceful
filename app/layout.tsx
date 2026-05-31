import type { Metadata } from "next";
import { JetBrains_Mono, Fraunces, Instrument_Sans } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
});

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sourceful — AI-Powered Document Intelligence",
  description:
    "Upload PDFs, DOCX, and text files, index them with embeddings, then ask document questions with cited retrieval and source review. Supports OpenAI and Google Gemini.",
  keywords: ["RAG", "document QA", "citations", "embeddings", "OpenAI", "Gemini", "PDF"],
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
      className={`${jetbrainsMono.variable} ${fraunces.variable} ${instrumentSans.variable} h-full`}
      // The pre-paint script below mutates `data-theme`, `data-contrast`,
      // `data-motion`, and `data-accent` on <html> from localStorage before
      // hydration. This is the canonical FOUC-prevention pattern; the
      // suppression is scoped to attributes on this element only.
      suppressHydrationWarning
    >
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
        {/* Apply theme before first paint to prevent flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var p=localStorage.getItem('rag-prefs');if(p){var d=JSON.parse(p);var r=document.documentElement;if(d.theme==='light')r.setAttribute('data-theme','light');if(d.highContrast)r.setAttribute('data-contrast','high');if(d.reducedMotion)r.setAttribute('data-motion','reduced');if(d.accentPack&&d.accentPack!=='terracotta')r.setAttribute('data-accent',d.accentPack);}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
