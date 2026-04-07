import type { NextConfig } from "next";

const backendUrl =
  process.env.BACKEND_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const base = `${backendUrl}/api`;
    return [
      { source: "/api/chat", destination: `${base}/chat` },
      { source: "/api/ingest", destination: `${base}/ingest` },
      { source: "/api/documents", destination: `${base}/documents` },
      { source: "/api/documents/:path*", destination: `${base}/documents/:path*` },
      { source: "/api/jobs/:path*", destination: `${base}/jobs/:path*` },
      { source: "/api/conversations", destination: `${base}/conversations` },
      { source: "/api/conversations/:path*", destination: `${base}/conversations/:path*` },
      { source: "/health", destination: `${backendUrl}/health` },
      { source: "/metrics", destination: `${backendUrl}/metrics` },
      { source: "/ready", destination: `${backendUrl}/ready` },
    ];
  },
};

export default nextConfig;
