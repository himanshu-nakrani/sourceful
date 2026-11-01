import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Sourceful — Traceable Document Intelligence",
    template: "%s · Sourceful",
  },
  description:
    "Upload PDFs, DOCX, and text files, index them with embeddings, then ask document questions with cited retrieval and source review. Self-hosted, BYOK, OpenAI and Gemini.",
  keywords: ["RAG", "document QA", "citations", "embeddings", "OpenAI", "Gemini", "PDF", "self-hosted"],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

/**
 * Root HTML layout that applies global fonts and a pre-paint theme selection.
 *
 * Injects an inline script that reads `localStorage.getItem('rag-prefs')`
 * and sets `document.documentElement`'s `data-theme`/`data-contrast`/
 * `data-motion`/`data-accent` attributes before the first paint so the
 * saved theme never flashes.
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
      className={`${inter.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable} h-full`}
      // The pre-paint script below mutates `data-theme`, `data-contrast`,
      // `data-motion`, and `data-accent` on <html> from localStorage before
      // hydration. This is the canonical FOUC-prevention pattern; the
      // suppression is scoped to attributes on this element only.
      suppressHydrationWarning
    >
      <head>
        {/*
          Apply theme before first paint to prevent Flash of Unstyled Content (FOUC).
          Security note: This is a standard, safe pattern. It only reads from localStorage,
          parses JSON, and sets predefined data attributes. It does not execute any
          user-controlled strings as code, and the try/catch prevents errors from invalid JSON.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var p=localStorage.getItem('rag-prefs');if(p){var d=JSON.parse(p);var r=document.documentElement;if(d.theme==='light')r.setAttribute('data-theme','light');if(d.highContrast)r.setAttribute('data-contrast','high');if(d.reducedMotion)r.setAttribute('data-motion','reduced');var pack=d.accentPack;if(pack==='emerald')pack='pulse';else if(pack==='amber')pack='beam';else if(pack==='terracotta')pack='lime';if(pack&&pack!=='lime')r.setAttribute('data-accent',pack);}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
