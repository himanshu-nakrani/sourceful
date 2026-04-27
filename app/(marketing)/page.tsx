"use client";

import React, { useRef } from "react";
import { motion, useInView } from "framer-motion";
import {
  FileText,
  MessageSquare,
  Shield,
  BarChart3,
  Users,
  Cloud,
  Database,
  Brain,
  ArrowRight,
  Sparkles,
  GitBranch,
  ChevronRight,
} from "lucide-react";
import Link from "next/link";

/* ─── Data ─────────────────────────────────────────────────────────── */

const features = [
  {
    icon: Brain,
    title: "Advanced RAG Pipeline",
    description:
      "Hybrid search with dense + FTS retrieval, cross-encoder reranking, MMR diversification, and query transformations.",
    color: "var(--accent-primary)",
    gradient: "linear-gradient(135deg, rgba(20,184,166,0.12), rgba(20,184,166,0.02))",
  },
  {
    icon: FileText,
    title: "Multi-Modal Ingestion",
    description:
      "PDFs, Office docs, images, tables, and scanned documents with OCR. Docling-powered extraction with layout preservation.",
    color: "var(--accent-secondary)",
    gradient: "linear-gradient(135deg, rgba(139,92,246,0.12), rgba(139,92,246,0.02))",
  },
  {
    icon: MessageSquare,
    title: "Agentic Retrieval",
    description:
      "GraphRAG with community detection, multi-hop traversal, and agent-driven search loops for complex queries.",
    color: "#3b82f6",
    gradient: "linear-gradient(135deg, rgba(59,130,246,0.12), rgba(59,130,246,0.02))",
  },
  {
    icon: Cloud,
    title: "Cloud Connectors",
    description:
      "Sync from Google Drive, Notion, Confluence, and S3. Automated background sync with change detection.",
    color: "#f59e0b",
    gradient: "linear-gradient(135deg, rgba(245,158,11,0.12), rgba(245,158,11,0.02))",
  },
  {
    icon: Shield,
    title: "Enterprise Security",
    description:
      "Workspace-based RBAC, shareable links with expiration, usage quotas, and comprehensive audit logging.",
    color: "#22c55e",
    gradient: "linear-gradient(135deg, rgba(34,197,94,0.12), rgba(34,197,94,0.02))",
  },
  {
    icon: BarChart3,
    title: "Observability",
    description:
      "Per-stage latency metrics, RAGAS evaluation, Prometheus metrics, and Langfuse tracing integration.",
    color: "#ec4899",
    gradient: "linear-gradient(135deg, rgba(236,72,153,0.12), rgba(236,72,153,0.02))",
  },
];

const techStack = [
  { name: "Next.js 14", category: "Frontend", icon: "▲" },
  { name: "FastAPI", category: "Backend", icon: "⚡" },
  { name: "PostgreSQL + pgvector", category: "Database", icon: "🗄️" },
  { name: "OpenAI / Gemini", category: "LLM", icon: "🧠" },
  { name: "Sentence Transformers", category: "Embeddings", icon: "📐" },
  { name: "Docling", category: "Document Parsing", icon: "📄" },
  { name: "NetworkX", category: "Graph Processing", icon: "🔗" },
  { name: "Cohere / Jina", category: "Reranking", icon: "🔀" },
  { name: "Langfuse", category: "Observability", icon: "📊" },
];

const stats = [
  { label: "Recall@5", value: "92%", suffix: "", prefix: "" },
  { label: "Faithfulness", value: "0.87", suffix: "", prefix: "" },
  { label: "p95 Latency", value: "<2.5s", suffix: "", prefix: "" },
  { label: "Retrieval Modes", value: "4", suffix: "+", prefix: "" },
];

const architectureLayers = [
  {
    icon: Database,
    title: "Ingestion Layer",
    color: "var(--accent-primary)",
    items: ["Docling extraction", "OCR + table detection", "Semantic chunking", "GraphRAG entities"],
  },
  {
    icon: Brain,
    title: "Retrieval Pipeline",
    color: "var(--accent-secondary)",
    items: ["Hybrid search", "Cross-encoder reranking", "MMR diversification", "Query transforms"],
  },
  {
    icon: Users,
    title: "Application Layer",
    color: "#3b82f6",
    items: ["Streaming chat", "Notebook UX", "Workspace RBAC", "Prompt library"],
  },
];

/* ─── Animated counter ─────────────────────────────────────────────── */

function AnimatedStat({ label, value, suffix = "" }: { label: string; value: string; suffix?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  return (
    <motion.div
      ref={ref}
      className="text-center"
      initial={{ opacity: 0, y: 16 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.5 }}
    >
      <div
        className="text-3xl md:text-4xl font-bold tracking-tight gradient-text"
        style={{ lineHeight: 1.1 }}
      >
        {value}{suffix}
      </div>
      <div
        className="text-sm mt-2 font-medium"
        style={{ color: "var(--text-tertiary)" }}
      >
        {label}
      </div>
    </motion.div>
  );
}

/* ─── Page ─────────────────────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div
      className="min-h-screen relative"
      style={{
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
      }}
    >
      {/* ─── Hero Section ───────────────────────────────────────────── */}
      <section className="relative overflow-hidden pt-16 pb-24 lg:pt-24 lg:pb-36">
        {/* Mesh gradient background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ opacity: 0.5 }}
        >
          <div
            className="absolute top-[-30%] left-[-20%] w-[700px] h-[700px] rounded-full animate-aurora"
            style={{
              background: "radial-gradient(circle, rgba(20,184,166,0.15), transparent 60%)",
              filter: "blur(60px)",
            }}
          />
          <div
            className="absolute top-[-10%] right-[-15%] w-[600px] h-[600px] rounded-full animate-aurora"
            style={{
              background: "radial-gradient(circle, rgba(139,92,246,0.12), transparent 60%)",
              filter: "blur(60px)",
              animationDelay: "-5s",
            }}
          />
          <div
            className="absolute bottom-[-20%] left-[30%] w-[500px] h-[500px] rounded-full animate-aurora"
            style={{
              background: "radial-gradient(circle, rgba(59,130,246,0.08), transparent 60%)",
              filter: "blur(60px)",
              animationDelay: "-10s",
            }}
          />
        </div>

        {/* Subtle grid */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)`,
            backgroundSize: "60px 60px",
            maskImage: "radial-gradient(ellipse 60% 60% at 50% 50%, black, transparent)",
            WebkitMaskImage: "radial-gradient(ellipse 60% 60% at 50% 50%, black, transparent)",
          }}
        />

        <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="text-center max-w-4xl mx-auto">
            {/* Badge */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium mb-8"
              style={{
                background: "var(--accent-primary-soft)",
                border: "1px solid var(--border-hover)",
                color: "var(--accent-primary)",
              }}
            >
              <Sparkles size={12} />
              Open Source RAG Platform
              <ChevronRight size={12} />
            </motion.div>

            {/* Title */}
            <motion.h1
              initial={{ opacity: 0, y: 20, filter: "blur(8px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.7, delay: 0.1 }}
              className="text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight"
              style={{ lineHeight: 1.05, letterSpacing: "-0.04em" }}
            >
              Document Intelligence
              <br />
              <span className="gradient-text">Powered by AI</span>
            </motion.h1>

            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.25 }}
              className="mt-6 text-lg md:text-xl max-w-2xl mx-auto"
              style={{ color: "var(--text-secondary)", lineHeight: 1.65 }}
            >
              Enterprise-grade RAG platform with hybrid retrieval, agentic
              capabilities, and production-ready observability. Built for teams
              that need{" "}
              <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                grounded answers
              </span>{" "}
              from their documents.
            </motion.p>

            {/* CTA buttons */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.4 }}
              className="mt-10 flex flex-col sm:flex-row gap-3 justify-center"
            >
              <Link
                href="/dashboard"
                className="group inline-flex items-center justify-center gap-2 px-7 py-3.5 text-base font-semibold rounded-xl transition-all duration-300"
                style={{
                  background: "var(--gradient-accent)",
                  color: "#fff",
                  boxShadow: "var(--shadow-glow-teal)",
                }}
              >
                Get Started
                <ArrowRight
                  size={16}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
              <a
                href="https://github.com/himanshu-nakrani/document-qa"
                className="inline-flex items-center justify-center gap-2 px-7 py-3.5 text-base font-semibold rounded-xl transition-all duration-200"
                style={{
                  background: "var(--bg-surface)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-hover)",
                }}
              >
                <GitBranch size={16} />
                View on GitHub
              </a>
            </motion.div>

            {/* Stats */}
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.6 }}
              className="mt-20 grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-12 max-w-3xl mx-auto"
            >
              {stats.map((item) => (
                <AnimatedStat key={item.label} {...item} />
              ))}
            </motion.div>
          </div>
        </div>
      </section>

      {/* ─── Features Bento Grid ───────────────────────────────────── */}
      <section
        className="py-20 lg:py-28 relative"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            className="text-center max-w-2xl mx-auto mb-16"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <span
              className="text-xs font-semibold uppercase tracking-widest mb-4 block"
              style={{ color: "var(--accent-primary)" }}
            >
              Capabilities
            </span>
            <h2
              className="text-3xl md:text-4xl font-bold tracking-tight"
              style={{ letterSpacing: "-0.03em" }}
            >
              Everything you need for
              <br />
              <span className="gradient-text">document intelligence</span>
            </h2>
            <p
              className="mt-4 text-base"
              style={{ color: "var(--text-secondary)", lineHeight: 1.65 }}
            >
              From ingestion to retrieval to conversation — every component is
              optimized for accuracy and performance.
            </p>
          </motion.div>

          <div className="bento-grid max-w-6xl mx-auto">
            {features.map((feature, index) => (
              <motion.div
                key={feature.title}
                className="bento-card group"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: index * 0.08 }}
              >
                <div
                  className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-xl"
                  style={{ background: feature.gradient }}
                />
                <div className="relative z-10">
                  <div
                    className="inline-flex items-center justify-center w-10 h-10 rounded-xl mb-4"
                    style={{
                      background: `${feature.color}15`,
                      border: `1px solid ${feature.color}25`,
                    }}
                  >
                    <feature.icon size={18} style={{ color: feature.color }} />
                  </div>
                  <h3
                    className="text-base font-semibold mb-2"
                    style={{ color: "var(--text-primary)", letterSpacing: "-0.01em" }}
                  >
                    {feature.title}
                  </h3>
                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "var(--text-tertiary)" }}
                  >
                    {feature.description}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Architecture ──────────────────────────────────────────── */}
      <section
        className="py-20 lg:py-28"
        style={{
          background: "var(--bg-secondary)",
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            className="text-center max-w-2xl mx-auto mb-16"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <span
              className="text-xs font-semibold uppercase tracking-widest mb-4 block"
              style={{ color: "var(--accent-secondary)" }}
            >
              Architecture
            </span>
            <h2
              className="text-3xl md:text-4xl font-bold tracking-tight"
              style={{ letterSpacing: "-0.03em" }}
            >
              Three layers.{" "}
              <span className="gradient-text">One pipeline.</span>
            </h2>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {architectureLayers.map((layer, index) => (
              <motion.div
                key={layer.title}
                className="rounded-2xl p-6 relative overflow-hidden group"
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                }}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: index * 0.1 }}
              >
                {/* Top accent line */}
                <div
                  className="absolute top-0 left-0 right-0 h-px opacity-60 group-hover:opacity-100 transition-opacity"
                  style={{
                    background: `linear-gradient(90deg, transparent, ${layer.color}, transparent)`,
                  }}
                />

                <div
                  className="inline-flex items-center justify-center w-12 h-12 rounded-xl mb-4"
                  style={{
                    background: `${layer.color}12`,
                    border: `1px solid ${layer.color}20`,
                  }}
                >
                  <layer.icon size={22} style={{ color: layer.color }} />
                </div>

                <h3 className="text-base font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
                  {layer.title}
                </h3>

                <ul className="space-y-2">
                  {layer.items.map((item) => (
                    <li
                      key={item}
                      className="flex items-center gap-2 text-sm"
                      style={{ color: "var(--text-tertiary)" }}
                    >
                      <div
                        className="w-1 h-1 rounded-full flex-shrink-0"
                        style={{ background: layer.color }}
                      />
                      {item}
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Tech Stack ────────────────────────────────────────────── */}
      <section className="py-20 lg:py-28">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            className="text-center max-w-2xl mx-auto mb-12"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <span
              className="text-xs font-semibold uppercase tracking-widest mb-4 block"
              style={{ color: "var(--accent-primary)" }}
            >
              Technology
            </span>
            <h2
              className="text-3xl font-bold tracking-tight"
              style={{ letterSpacing: "-0.03em" }}
            >
              Built with{" "}
              <span className="gradient-text">modern tools</span>
            </h2>
          </motion.div>

          <div className="flex flex-wrap justify-center gap-3 max-w-4xl mx-auto">
            {techStack.map((tech, i) => (
              <motion.span
                key={tech.name}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200"
                style={{
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.3, delay: i * 0.04 }}
                whileHover={{
                  borderColor: "var(--border-accent)",
                  y: -2,
                }}
              >
                {tech.name}
                <span
                  className="text-xs px-2 py-0.5 rounded-md"
                  style={{
                    background: "var(--bg-elevated)",
                    color: "var(--text-muted)",
                  }}
                >
                  {tech.category}
                </span>
              </motion.span>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA Section ───────────────────────────────────────────── */}
      <section
        className="py-24 lg:py-32 relative overflow-hidden"
        style={{
          borderTop: "1px solid var(--border)",
        }}
      >
        {/* Gradient background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "var(--gradient-accent-soft)",
            opacity: 0.5,
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `radial-gradient(circle at 50% 50%, var(--accent-primary-glow), transparent 70%)`,
          }}
        />

        <div className="container mx-auto px-4 sm:px-6 lg:px-8 text-center relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <h2
              className="text-3xl md:text-5xl font-bold tracking-tight mb-6"
              style={{ letterSpacing: "-0.03em" }}
            >
              Ready to get{" "}
              <span className="gradient-text">started?</span>
            </h2>
            <p
              className="text-lg mb-10 max-w-xl mx-auto"
              style={{ color: "var(--text-secondary)", lineHeight: 1.65 }}
            >
              Deploy your own instance in minutes with Docker Compose, or jump
              straight into the demo.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link
                href="/dashboard"
                className="group inline-flex items-center justify-center gap-2 px-8 py-4 text-base font-semibold rounded-xl transition-all duration-300"
                style={{
                  background: "var(--gradient-accent)",
                  color: "#fff",
                  boxShadow: "var(--shadow-glow-teal)",
                }}
              >
                Launch App
                <ArrowRight
                  size={16}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
              <a
                href="/docs"
                className="inline-flex items-center justify-center gap-2 px-8 py-4 text-base font-semibold rounded-xl transition-all duration-200"
                style={{
                  background: "var(--bg-surface)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-hover)",
                }}
              >
                Documentation
              </a>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─── Footer ────────────────────────────────────────────────── */}
      <footer
        className="py-10"
        style={{
          borderTop: "1px solid var(--border)",
          background: "var(--bg-secondary)",
        }}
      >
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex items-center gap-3">
              <div
                className="flex items-center justify-center w-8 h-8 rounded-lg"
                style={{
                  background: "var(--accent-primary-soft)",
                  border: "1px solid var(--border)",
                }}
              >
                <FileText size={14} style={{ color: "var(--accent-primary)" }} />
              </div>
              <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                DocRAG
              </span>
            </div>
            <div className="flex gap-6 text-sm">
              <a
                href="https://github.com/himanshu-nakrani/document-qa"
                className="transition-colors"
                style={{ color: "var(--text-tertiary)" }}
              >
                GitHub
              </a>
              <a
                href="/docs"
                className="transition-colors"
                style={{ color: "var(--text-tertiary)" }}
              >
                Docs
              </a>
              <Link
                href="/dashboard"
                className="transition-colors"
                style={{ color: "var(--text-tertiary)" }}
              >
                App
              </Link>
            </div>
          </div>
          <div
            className="mt-6 text-center text-xs"
            style={{ color: "var(--text-muted)" }}
          >
            Built by Himanshu Nakrani. Open source under MIT license.
          </div>
        </div>
      </footer>
    </div>
  );
}
