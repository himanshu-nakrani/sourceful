"use client";

import React from "react";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Database,
  FileText,
  GitBranch,
  Layers3,
  LockKeyhole,
  MessageSquare,
  Search,
  Server,
  Shield,
} from "lucide-react";
import Link from "next/link";

const trustSignals = [
  { label: "Cited responses", value: "Chunk-level" },
  { label: "Retrieval audit", value: "Stage-by-stage" },
  { label: "Workspace access", value: "Role scoped" },
  { label: "Deployment", value: "Self-hostable" },
];

const provenanceRows = [
  {
    title: "Board Report Q3.pdf",
    detail: "p.12 · revenue bridge and margin variance",
    score: "0.92",
    status: "strong",
  },
  {
    title: "Security Review Notes.docx",
    detail: "section 4 · vendor access controls",
    score: "0.84",
    status: "strong",
  },
  {
    title: "Support Export.csv",
    detail: "rows 184-209 · incident recurrence",
    score: "0.71",
    status: "review",
  },
];

const workflow = [
  {
    icon: Database,
    title: "Ingest with structure",
    description: "Documents keep useful layout, page anchors, tables, and workspace ownership through the pipeline.",
  },
  {
    icon: Search,
    title: "Retrieve with evidence",
    description: "Hybrid retrieval, reranking, and source filters expose why an answer was assembled.",
  },
  {
    icon: Shield,
    title: "Answer with traceability",
    description: "Responses carry citations, confidence rails, feedback, and saved workspace artifacts.",
  },
];

const stack = [
  { name: "Next.js", role: "Interface" },
  { name: "FastAPI", role: "API" },
  { name: "Postgres + pgvector", role: "Storage" },
  { name: "Docling", role: "Extraction" },
  { name: "Hybrid search", role: "Retrieval" },
  { name: "Langfuse", role: "Tracing" },
];

function ProductPreview() {
  return (
    <motion.div
      className="relative overflow-hidden rounded-xl"
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-hover)",
        boxShadow: "var(--shadow-lg)",
      }}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.65, delay: 0.2 }}
    >
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2">
          <div
            className="flex h-7 w-7 items-center justify-center rounded-md"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              color: "var(--accent-primary)",
            }}
          >
            <FileText size={14} />
          </div>
          <div>
            <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Acme diligence workspace
            </p>
            <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              14 documents · 2,846 chunks · private session
            </p>
          </div>
        </div>
        <div
          className="hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium sm:flex"
          style={{
            color: "var(--confidence-high)",
            background: "var(--confidence-high-soft)",
            border: "1px solid var(--border)",
          }}
        >
          <CheckCircle2 size={12} />
          Grounded
        </div>
      </div>

      <div className="grid min-h-[440px] grid-cols-1 lg:grid-cols-[230px_1fr]">
        <aside
          className="hidden border-r px-3 py-4 lg:block"
          style={{ borderColor: "var(--border)", background: "var(--bg-primary)" }}
        >
          <p className="mb-3 px-2 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Source set
          </p>
          {["Board Report Q3.pdf", "Security Review Notes.docx", "Support Export.csv"].map((doc, index) => (
            <div
              key={doc}
              className="mb-1.5 rounded-lg px-3 py-2"
              style={{
                background: index === 0 ? "var(--bg-surface)" : "transparent",
                border: `1px solid ${index === 0 ? "var(--border-hover)" : "transparent"}`,
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: index === 2 ? "var(--warning)" : "var(--success)" }}
                />
                <span className="truncate text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                  {doc}
                </span>
              </div>
              <p className="mt-1 text-[11px]" style={{ color: "var(--text-muted)" }}>
                ready · {index === 0 ? "412" : index === 1 ? "286" : "1,044"} chunks
              </p>
            </div>
          ))}
        </aside>

        <div className="px-4 py-5 sm:px-6">
          <div className="max-w-2xl">
            <div
              className="mb-4 rounded-xl px-4 py-3"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            >
              <div className="mb-2 flex items-center gap-2 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                <MessageSquare size={13} />
                What changed in vendor risk since the last review?
              </div>
              <p className="text-sm leading-6" style={{ color: "var(--text-primary)" }}>
                Vendor concentration increased in two critical workflows, but the current access review shows compensating controls for finance exports and incident response. The unresolved gap is recurring manual approval for support escalations.
              </p>
            </div>

            <div
              className="mb-5 rounded-xl px-4 py-3 confidence-high-rail"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
            >
              <div className="mb-3 flex items-center justify-between gap-3">
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                  Assistant answer
                </span>
                <span className="text-[11px]" style={{ color: "var(--confidence-high)" }}>
                  avg retrieval 82%
                </span>
              </div>
              <p className="text-sm leading-7" style={{ color: "var(--text-primary)" }}>
                The highest-risk change is not a new vendor. It is a broader dependency on existing vendors across revenue operations and customer support, with evidence in the Q3 board report and the security review notes.
                <span
                  className="mx-1 inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
                  style={{ color: "var(--accent-primary)", background: "var(--accent-primary-soft)", border: "1px solid var(--border)" }}
                >
                  1
                </span>
                The support export adds a weaker signal that escalations are recurring in the same queue.
                <span
                  className="mx-1 inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
                  style={{ color: "var(--warning)", background: "var(--warning-soft)", border: "1px solid var(--border)" }}
                >
                  3
                </span>
              </p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            {provenanceRows.map((row) => (
              <div
                key={row.title}
                className="rounded-lg px-3 py-3"
                style={{ background: "var(--bg-primary)", border: "1px solid var(--border)" }}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <FileText size={13} style={{ color: "var(--text-tertiary)" }} />
                  <span
                    className="text-[10px] font-semibold"
                    style={{ color: row.status === "strong" ? "var(--success)" : "var(--warning)" }}
                  >
                    {row.score}
                  </span>
                </div>
                <p className="truncate text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                  {row.title}
                </p>
                <p className="mt-1 line-clamp-2 text-[11px] leading-4" style={{ color: "var(--text-muted)" }}>
                  {row.detail}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default function LandingPage() {
  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--bg-primary)", color: "var(--text-primary)" }}
    >
      <section className="relative overflow-hidden px-4 pt-16 pb-18 sm:px-6 lg:px-8 lg:pt-20 lg:pb-24">
        <div
          className="absolute inset-x-0 top-0 h-px"
          style={{ background: "linear-gradient(90deg, transparent, var(--border-strong), transparent)" }}
        />
        <div className="container mx-auto">
          <div className="mx-auto grid max-w-7xl items-center gap-12 lg:grid-cols-[0.78fr_1.22fr]">
            <div>
              <motion.div
                className="mb-7 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  color: "var(--text-secondary)",
                }}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
              >
                <LockKeyhole size={12} />
                Self-hostable document QA workspace
              </motion.div>

              <motion.h1
                className="text-5xl font-semibold tracking-tight sm:text-6xl lg:text-7xl"
                style={{ lineHeight: 0.98, letterSpacing: "-0.045em" }}
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.65, delay: 0.08 }}
              >
                Answers you can trace back to the page.
              </motion.h1>

              <motion.p
                className="mt-6 max-w-xl text-base leading-8 sm:text-lg"
                style={{ color: "var(--text-secondary)" }}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.18 }}
              >
                DocRAG turns private document collections into a research workspace where every answer carries citations, retrieval context, and a review trail.
              </motion.p>

              <motion.div
                className="mt-9 flex flex-col gap-3 sm:flex-row"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, delay: 0.3 }}
              >
                <Link
                  href="/dashboard"
                  className="group inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold transition-all duration-200"
                  style={{
                    background: "var(--accent)",
                    color: "var(--accent-fg)",
                    boxShadow: "var(--shadow-sm)",
                  }}
                >
                  Open workspace
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </Link>
                <a
                  href="https://github.com/himanshu-nakrani/document-qa"
                  className="inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold transition-colors"
                  style={{
                    background: "var(--bg-secondary)",
                    color: "var(--text-primary)",
                    border: "1px solid var(--border-hover)",
                  }}
                >
                  <GitBranch size={15} />
                  Inspect source
                </a>
              </motion.div>

              <motion.div
                className="mt-10 grid grid-cols-2 gap-3"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, delay: 0.42 }}
              >
                {trustSignals.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-lg px-3 py-3"
                    style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                  >
                    <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                      {item.label}
                    </p>
                    <p className="mt-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                      {item.value}
                    </p>
                  </div>
                ))}
              </motion.div>
            </div>

            <ProductPreview />
          </div>
        </div>
      </section>

      <section
        className="border-y px-4 py-18 sm:px-6 lg:px-8 lg:py-24"
        style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
      >
        <div className="container mx-auto max-w-6xl">
          <div className="mb-10 max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              Provenance as interface
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl" style={{ letterSpacing: "-0.03em" }}>
              The premium layer is evidence, not decoration.
            </h2>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {workflow.map((item) => (
              <motion.div
                key={item.title}
                className="rounded-xl px-5 py-5"
                style={{ background: "var(--bg-primary)", border: "1px solid var(--border)" }}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.45 }}
              >
                <div
                  className="mb-5 flex h-9 w-9 items-center justify-center rounded-lg"
                  style={{ color: "var(--accent-primary)", background: "var(--accent-primary-soft)", border: "1px solid var(--border)" }}
                >
                  <item.icon size={17} />
                </div>
                <h3 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
                  {item.title}
                </h3>
                <p className="mt-3 text-sm leading-6" style={{ color: "var(--text-tertiary)" }}>
                  {item.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 py-18 sm:px-6 lg:px-8 lg:py-24">
        <div className="container mx-auto grid max-w-6xl gap-10 lg:grid-cols-[0.85fr_1.15fr]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              Operational clarity
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl" style={{ letterSpacing: "-0.03em" }}>
              Built for teams that need to defend the answer.
            </h2>
            <p className="mt-5 text-sm leading-7" style={{ color: "var(--text-secondary)" }}>
              The interface prioritizes citations, source quality, workspace controls, and retrieval diagnostics so users can move from answer to evidence without leaving the flow.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { icon: Layers3, title: "Mode-aware research", body: "Ask, compare, extract, and brief flows use the same citation-first system." },
              { icon: BarChart3, title: "Trust analytics", body: "Latency, retrieval stages, feedback, and grounding quality stay visible when needed." },
              { icon: Activity, title: "Durable ingestion", body: "Upload and background worker states make document readiness explicit." },
              { icon: Server, title: "Production path", body: "Postgres + pgvector, Docker Compose, and deployment notes are first-class." },
            ].map((item) => (
              <div
                key={item.title}
                className="rounded-xl px-4 py-4"
                style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
              >
                <item.icon size={16} style={{ color: "var(--text-secondary)" }} />
                <h3 className="mt-4 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-6" style={{ color: "var(--text-tertiary)" }}>
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section
        className="border-y px-4 py-14 sm:px-6 lg:px-8"
        style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
      >
        <div className="container mx-auto flex max-w-6xl flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              Stack
            </p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight" style={{ letterSpacing: "-0.025em" }}>
              Familiar pieces, composed for accountable retrieval.
            </h2>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:min-w-[520px]">
            {stack.map((item) => (
              <div
                key={item.name}
                className="flex items-center justify-between rounded-lg px-3 py-2.5"
                style={{ background: "var(--bg-primary)", border: "1px solid var(--border)" }}
              >
                <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                  {item.name}
                </span>
                <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                  {item.role}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 py-18 text-center sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl" style={{ letterSpacing: "-0.03em" }}>
            Start with a document. Leave with a source trail.
          </h2>
          <p className="mt-5 text-sm leading-7" style={{ color: "var(--text-secondary)" }}>
            Launch the workspace, connect a provider key, and verify answers against the documents that produced them.
          </p>
          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold"
              style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
            >
              Launch DocRAG
              <ArrowRight size={15} />
            </Link>
            <a
              href="https://github.com/himanshu-nakrani/document-qa"
              className="inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold"
              style={{ background: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border-hover)" }}
            >
              <GitBranch size={15} />
              GitHub
            </a>
          </div>
        </div>
      </section>

      <footer
        className="border-t px-4 py-8 sm:px-6 lg:px-8"
        style={{ borderColor: "var(--border)", background: "var(--bg-secondary)" }}
      >
        <div className="container mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 md:flex-row">
          <div className="flex items-center gap-3">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-lg"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--accent-primary)" }}
            >
              <FileText size={14} />
            </div>
            <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              DocRAG
            </span>
          </div>
          <div className="flex gap-6 text-sm">
            <a href="https://github.com/himanshu-nakrani/document-qa" style={{ color: "var(--text-tertiary)" }}>
              GitHub
            </a>
            <a href="/docs" style={{ color: "var(--text-tertiary)" }}>
              Docs
            </a>
            <Link href="/dashboard" style={{ color: "var(--text-tertiary)" }}>
              App
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
