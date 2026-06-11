import type { NextConfig } from "next";

const backendUrl =
  process.env.BACKEND_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const base = `${backendUrl}/api`;
    return [
      { source: "/api/auth/:path*", destination: `${base}/auth/:path*` },
      { source: "/api/chat", destination: `${base}/chat` },
      { source: "/api/chat/:path*", destination: `${base}/chat/:path*` },
      { source: "/api/ingest", destination: `${base}/ingest` },
      { source: "/api/documents", destination: `${base}/documents` },
      { source: "/api/documents/:path*", destination: `${base}/documents/:path*` },
      { source: "/api/jobs/:path*", destination: `${base}/jobs/:path*` },
      { source: "/api/conversations", destination: `${base}/conversations` },
      { source: "/api/conversations/:path*", destination: `${base}/conversations/:path*` },
      { source: "/api/users", destination: `${base}/users` },
      { source: "/api/users/:path*", destination: `${base}/users/:path*` },
      { source: "/api/analytics/:path*", destination: `${base}/analytics/:path*` },
      { source: "/api/models", destination: `${base}/models` },
      { source: "/api/workspaces", destination: `${base}/workspaces` },
      { source: "/api/workspaces/:path*", destination: `${base}/workspaces/:path*` },
      { source: "/api/feedback", destination: `${base}/feedback` },
      { source: "/api/feedback/:path*", destination: `${base}/feedback/:path*` },
      { source: "/health", destination: `${backendUrl}/health` },
      { source: "/metrics", destination: `${backendUrl}/metrics` },
      { source: "/ready", destination: `${backendUrl}/ready` },
    ];
  },
};

export default nextConfig;
