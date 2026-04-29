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

/* ─── Feature data ───────────────────────────────────────────────── */

const features = [
  {
    icon: Brain,
    title: "Advanced RAG Pipeline",
    description:
      "Hybrid search combining dense vectors with full-text, cross-encoder reranking, MMR diversification, and multi-query transformations for precise retrieval.",
    accent: "var(--mk-terracotta)",
  },
  {
    icon: FileText,
    title: "Multi-Modal Ingestion",
    description:
      "PDFs, DOCX, spreadsheets, presentations, scanned documents with OCR. Layout-preserving extraction powered by Docling.",
    accent: "var(--mk-sage)",
  },
  {
    icon: MessageSquare,
    title: "Agentic Retrieval",
    description:
      "GraphRAG with community detection and multi-hop traversal. Agent-driven search loops adapt to complex, multi-step queries.",
    accent: "#3B82F6",
  },
  {
    icon: Cloud,
    title: "Cloud Connectors",
    description:
      "Sync documents from Google Drive, Notion, Confluence, and S3. Automated background refresh with change detection.",
    accent: "var(--mk-sunset)",
  },
  {
    icon: Shield,
    title: "Enterprise Security",
    description:
      "Workspace-based RBAC with owner, admin, editor, and viewer roles. Shareable links with configurable expiration and usage quotas.",
    accent: "var(--mk-sage)",
  },
  {
    icon: BarChart3,
    title: "Full Observability",
    description:
      "Per-stage latency metrics, RAGAS evaluation scoring, Prometheus metrics endpoint, and Langfuse tracing for every query.",
    accent: "#8B5CF6",
  },
];

const techStack = [
  { name: "Next.js", category: "Frontend" },
  { name: "FastAPI", category: "Backend" },
  { name: "PostgreSQL + pgvector", category: "Database" },
  { name: "OpenAI / Gemini", category: "LLM" },
  { name: "Docling", category: "Parsing" },
  { name: "Sentence Transformers", category: "Embeddings" },
  { name: "NetworkX", category: "Graph" },
  { name: "Cohere / Jina", category: "Reranking" },
  { name: "Langfuse", category: "Tracing" },
];

const stats = [
  { label: "Recall@5", value: "92%", prefix: "", suffix: "" },
  { label: "Faithfulness", value: "0.87", prefix: "", suffix: "" },
  { label: "p95 Latency", value: "<2.5s", prefix: "", suffix: "" },
  { label: "Retrieval Modes", value: "4", prefix: "", suffix: "+" },
];

/* ─── Animated Stat ──────────────────────────────────────────────── */

function AnimatedStat({
  label,
  value,
  prefix = "",
  suffix = "",
}: {
  label: string;
  value: string;
  prefix?: string;
  suffix?: string;
}) {
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
        className="text-3xl md:text-4xl font-bold gradient-text"
        style={{
          fontFamily: "var(--font-fraunces), serif",
          letterSpacing: "-0.03em",
        }}
      >
        {prefix}
        {value}
        {suffix}
      </div>
      <div
        className="text-sm mt-2 font-medium"
        style={{ color: "var(--text-tertiary)", fontFamily: "var(--font-instrument-sans), sans-serif" }}
      >
        {label}
      </div>
    </motion.div>
  );
}

/* ─── InView Reveal ──────────────────────────────────────────────── */

function InViewReveal({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <motion.div
      ref={ref}
      className={className}
      initial={{ opacity: 0, y: 24 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

/* ─── Page ───────────────────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div>
      {/* ═══════════════════════════════════════════════════════════════
          H E R O
          ════════════════════════════════════════════════════════════ */}
      <section className="relative overflow-hidden pt-28 pb-20 lg:pt-40 lg:pb-28">
        {/* Warm organic blobs */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="warm-blob warm-blob-terracotta top-[-25%] right-[-15%] w-[700px] h-[700px] animate-aurora" />
          <div
            className="warm-blob warm-blob-sage top-[30%] left-[-10%] w-[500px] h-[500px] animate-aurora"
            style={{ animationDelay: "-7s" }}
          />
          <div
            className="warm-blob warm-blob-sunset bottom-[-15%] right-[20%] w-[600px] h-[600px] animate-aurora"
            style={{ animationDelay: "-12s" }}
          />
        </div>

        {/* Dot grid pattern */}
        <div
          className="absolute inset-0 pointer-events-none dot-grid"
          style={{ maskImage: "radial-gradient(ellipse 65% 65% at 50% 40%, black, transparent)", WebkitMaskImage: "radial-gradient(ellipse 65% 65% at 50% 40%, black, transparent)" }}
        />

        <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="max-w-3xl">
            {/* Badge */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-sm font-medium mb-8"
              style={{
                background: "var(--accent-primary-soft)",
                border: "1px solid var(--border-hover)",
                color: "var(--accent-primary)",
                fontFamily: "var(--font-instrument-sans), sans-serif",
              }}
            >
              <Sparkles size={13} />
              Open Source RAG Platform
              <ChevronRight size={13} />
            </motion.div>

            {/* Heading */}
            <motion.h1
              initial={{ opacity: 0, y: 28, filter: "blur(12px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.8, delay: 0.1 }}
              className="editorial-display text-5xl md:text-6xl lg:text-7xl"
            >
              Intelligence
              <br />
              <span className="gradient-text">for your documents</span>
            </motion.h1>

            {/* Accent line */}
            <motion.div
              initial={{ opacity: 0, scaleX: 0 }}
              animate={{ opacity: 1, scaleX: 1 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="accent-divider mt-8 mb-8"
              style={{ transformOrigin: "left" }}
            />

            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="text-lg md:text-xl max-w-xl"
              style={{
                color: "var(--text-secondary)",
                lineHeight: 1.75,
                fontFamily: "var(--font-instrument-sans), sans-serif",
              }}
            >
              Enterprise-grade retrieval augmented generation with hybrid search,
              agentic capabilities, and production-ready observability — designed
              for teams that demand{" "}
              <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
                grounded answers
              </span>{" "}
              from their knowledge base.
            </motion.p>

            {/* CTA buttons */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.5 }}
              className="flex flex-col sm:flex-row gap-3 mt-9"
            >
              <Link href="/dashboard" className="btn-primary-warm group">
                Get Started
                <ArrowRight
                  size={16}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
              <a
                href="https://github.com/himanshu-nakrani/document-qa"
                className="btn-outline-warm"
              >
                <GitBranch size={16} />
                View on GitHub
              </a>
            </motion.div>

            {/* Stats strip */}
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.7 }}
              className="mt-20 pt-8 grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-12"
              style={{ borderTop: "1px solid var(--border)" }}
            >
              {stats.map((item) => (
                <AnimatedStat key={item.label} {...item} />
              ))}
            </motion.div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════
          F E A T U R E S
          ════════════════════════════════════════════════════════════ */}
      <section
        className="py-20 lg:py-28"
        style={{ background: "var(--bg-secondary)", borderTop: "1px solid var(--border)" }}
      >
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <InViewReveal className="mb-16">
            <span
              className="text-sm font-semibold uppercase tracking-[0.2em] mb-4 block"
              style={{ color: "var(--accent-primary)", fontFamily: "var(--font-instrument-sans), sans-serif" }}
            >
              Capabilities
            </span>
            <h2
              className="editorial-heading text-3xl md:text-5xl lg:text-5xl"
              style={{ fontFamily: "var(--font-fraunces), serif" }}
            >
              Everything you need for
              <br />
              <span className="gradient-text">document intelligence</span>
            </h2>
            <div className="accent-divider-sm mt-6" />
            <p
              className="mt-5 text-base max-w-lg"
              style={{ color: "var(--text-secondary)", lineHeight: 1.7 }}
            >
              From ingestion to retrieval to conversation — every layer is
              optimized for precision, speed, and trust.
            </p>
          </InViewReveal>

          {/* Feature cards — 3 columns on desktop */}
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5 max-w-6xl mx-auto">
            {features.map((feature, index) => (
              <InViewReveal key={feature.title} delay={index * 0.08}>
                <div className="feature-card bg-white">
                  {/* Icon */}
                  <div
                    className="inline-flex items-center justify-center w-10 h-10 rounded-xl mb-5"
                    style={{
                      background: `${feature.accent}10`,
                      border: `1px solid ${feature.accent}20`,
                    }}
                  >
                    <feature.icon size={18} style={{ color: feature.accent }} />
                  </div>

                  <h3
                    className="text-base font-semibold mb-3"
                    style={{
                      fontFamily: "var(--font-fraunces), serif",
                      letterSpacing: "-0.01em",
                      color: "var(--text-primary)",
                    }}
                  >
                    {feature.title}
                  </h3>

                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "var(--text-tertiary)", lineHeight: 1.65 }}
                  >
                    {feature.description}
                  </p>
                </div>
              </InViewReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════
          A R C H I T E C T U R E
          ════════════════════════════════════════════════════════════ */}
      <section className="py-20 lg:py-28" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <InViewReveal className="text-center max-w-2xl mx-auto mb-16">
            <span
              className="text-sm font-semibold uppercase tracking-[0.2em] mb-4 block"
              style={{ color: "var(--accent-secondary)", fontFamily: "var(--font-instrument-sans), sans-serif" }}
            >
              Architecture
            </span>
            <h2
              className="editorial-heading text-3xl md:text-5xl text-center"
              style={{ fontFamily: "var(--font-fraunces), serif" }}
            >
              Three layers.{" "}
              <span className="gradient-text">One pipeline.</span>
            </h2>
            <div
              className="accent-divider-sm mt-6 mx-auto"
              style={{ marginLeft: "auto", marginRight: "auto" }}
            />
          </InViewReveal>

          <div className="max-w-3xl mx-auto space-y-0">
            {/* Layer 1 */}
            <InViewReveal delay={0} className="timeline-step pb-8">
              <div className="flex items-start gap-4">
                <div
                  className="inline-flex items-center justify-center w-11 h-11 rounded-xl flex-shrink-0 mt-0.5"
                  style={{
                    background: "rgba(211, 93, 71, 0.08)",
                    border: "1px solid rgba(211, 93, 71, 0.15)",
                  }}
                >
                  <Database size={20} style={{ color: "var(--mk-terracotta)" }} />
                </div>
                <div>
                  <h3
                    className="text-lg font-semibold mb-2"
                    style={{
                      fontFamily: "var(--font-fraunces), serif",
                      color: "var(--text-primary)",
                    }}
                  >
                    Ingestion Layer
                  </h3>
                  <p className="text-sm" style={{ color: "var(--text-tertiary)", lineHeight: 1.7 }}>
                    Docling-powered extraction with layout preservation, OCR, and table detection.
                    Documents are semantically chunked and enriched with GraphRAG entity extraction.
                  </p>
                </div>
              </div>
            </InViewReveal>

            {/* Layer 2 */}
            <InViewReveal delay={0.1} className="timeline-step pb-8">
              <div className="flex items-start gap-4">
                <div
                  className="inline-flex items-center justify-center w-11 h-11 rounded-xl flex-shrink-0 mt-0.5"
                  style={{
                    background: "rgba(74, 124, 89, 0.08)",
                    border: "1px solid rgba(74, 124, 89, 0.15)",
                  }}
                >
                  <Brain size={20} style={{ color: "var(--mk-sage)" }} />
                </div>
                <div>
                  <h3
                    className="text-lg font-semibold mb-2"
                    style={{
                      fontFamily: "var(--font-fraunces), serif",
                      color: "var(--text-primary)",
                    }}
                  >
                    Retrieval Pipeline
                  </h3>
                  <p className="text-sm" style={{ color: "var(--text-tertiary)", lineHeight: 1.7 }}>
                    Dense vector search combined with reciprocal rank fusion from a full-text lane.
                    Cross-encoder reranking, MMR diversification, and optional HyDE + multi-query transforms.
                  </p>
                </div>
              </div>
            </InViewReveal>

            {/* Layer 3 */}
            <InViewReveal delay={0.2} className="timeline-step">
              <div className="flex items-start gap-4">
                <div
                  className="inline-flex items-center justify-center w-11 h-11 rounded-xl flex-shrink-0 mt-0.5"
                  style={{
                    background: "rgba(59, 130, 246, 0.08)",
                    border: "1px solid rgba(59, 130, 246, 0.15)",
                  }}
                >
                  <Users size={20} style={{ color: "#3B82F6" }} />
                </div>
                <div>
                  <h3
                    className="text-lg font-semibold mb-2"
                    style={{
                      fontFamily: "var(--font-fraunces), serif",
                      color: "var(--text-primary)",
                    }}
                  >
                    Application Layer
                  </h3>
                  <p className="text-sm" style={{ color: "var(--text-tertiary)", lineHeight: 1.7 }}>
                    Streaming chat with SSE, interactive document notebook,
                    workspace-based RBAC, shareable links, and a configurable prompt library.
                  </p>
                </div>
              </div>
            </InViewReveal>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════
          T E C H   S T A C K
          ════════════════════════════════════════════════════════════ */}
      <section
        className="py-20 lg:py-28"
        style={{ background: "var(--bg-secondary)", borderTop: "1px solid var(--border)" }}
      >
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <InViewReveal className="text-center max-w-2xl mx-auto mb-12">
            <span
              className="text-sm font-semibold uppercase tracking-[0.2em] mb-4 block"
              style={{ color: "var(--accent-primary)", fontFamily: "var(--font-instrument-sans), sans-serif" }}
            >
              Technology
            </span>
            <h2
              className="editorial-heading text-3xl md:text-4xl text-center"
              style={{ fontFamily: "var(--font-fraunces), serif" }}
            >
              Built with{" "}
              <span className="gradient-text">modern tools</span>
            </h2>
          </InViewReveal>

          <div className="flex flex-wrap justify-center gap-3 max-w-3xl mx-auto">
            {techStack.map((tech, i) => (
              <InViewReveal key={tech.name} delay={i * 0.04}>
                <span className="tech-pill">
                  <span>{tech.name}</span>
                  <span
                    className="text-xs px-2 py-0.5 rounded-md font-medium"
                    style={{
                      background: "var(--bg-secondary)",
                      color: "var(--text-muted)",
                    }}
                  >
                    {tech.category}
                  </span>
                </span>
              </InViewReveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════
          C T A
          ════════════════════════════════════════════════════════════ */}
      <section className="py-24 lg:py-32 relative overflow-hidden">
        {/* Warm gradient background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "var(--gradient-accent-soft)",
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "radial-gradient(circle at 50% 50%, rgba(211, 93, 71, 0.06), transparent 70%)",
          }}
        />

        <div className="container mx-auto px-4 sm:px-6 lg:px-8 text-center relative z-10">
          <InViewReveal>
            <h2
              className="editorial-display text-3xl md:text-5xl lg:text-6xl mb-6"
              style={{ fontFamily: "var(--font-fraunces), serif" }}
            >
              Ready to get{" "}
              <span className="gradient-text">started?</span>
            </h2>
            <p
              className="text-lg mb-10 max-w-lg mx-auto"
              style={{ color: "var(--text-secondary)", lineHeight: 1.7 }}
            >
              Deploy your own instance in minutes with Docker Compose, or explore
              the demo to see what your documents can reveal.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link href="/dashboard" className="btn-primary-warm text-lg px-8 py-4">
                Launch App
                <ArrowRight size={18} />
              </Link>
              <a href="/docs" className="btn-outline-warm text-lg px-8 py-4">
                Documentation
              </a>
            </div>
          </InViewReveal>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════
          F O O T E R
          ════════════════════════════════════════════════════════════ */}
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
              <span
                className="font-semibold text-sm"
                style={{
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-fraunces), serif",
                }}
              >
                DocRAG
              </span>
            </div>
            <div
              className="flex gap-6 text-sm"
              style={{ fontFamily: "var(--font-instrument-sans), sans-serif" }}
            >
              <a
                href="https://github.com/himanshu-nakrani/document-qa"
                className="transition-colors hover:opacity-70"
                style={{ color: "var(--text-tertiary)" }}
              >
                GitHub
              </a>
              <a
                href="/docs"
                className="transition-colors hover:opacity-70"
                style={{ color: "var(--text-tertiary)" }}
              >
                Docs
              </a>
              <Link
                href="/dashboard"
                className="transition-colors hover:opacity-70"
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
