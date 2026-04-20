"use client";

import React from "react";
import { motion } from "framer-motion";
import {
  FileText,
  MessageSquare,
  Zap,
  Shield,
  BarChart3,
  Users,
  Cloud,
  Database,
  Brain,
  ArrowRight,
  Check,
} from "lucide-react";
import Link from "next/link";

const features = [
  {
    icon: Brain,
    title: "Advanced RAG Pipeline",
    description: "Hybrid search (dense + FTS), cross-encoder reranking, MMR diversification, and query transformations (HyDE, multi-query, step-back).",
  },
  {
    icon: FileText,
    title: "Multi-Modal Ingestion",
    description: "PDFs, Office docs, images, tables, and scanned documents with OCR. Docling-powered extraction with layout preservation.",
  },
  {
    icon: MessageSquare,
    title: "Agentic Retrieval",
    description: "GraphRAG with community detection, multi-hop traversal, and agent-driven search loops for complex queries.",
  },
  {
    icon: Cloud,
    title: "Cloud Connectors",
    description: "Sync from Google Drive, Notion, Confluence, and S3. Automated background sync with change detection.",
  },
  {
    icon: Shield,
    title: "Enterprise Security",
    description: "Workspace-based RBAC, shareable links with expiration, usage quotas, and audit logging.",
  },
  {
    icon: BarChart3,
    title: "Observability",
    description: "Per-stage latency metrics, RAGAS evaluation, Prometheus metrics, and Langfuse tracing integration.",
  },
];

const techStack = [
  { name: "Next.js 14", category: "Frontend" },
  { name: "FastAPI", category: "Backend" },
  { name: "PostgreSQL + pgvector", category: "Database" },
  { name: "SQLite (dev)", category: "Database" },
  { name: "OpenAI / Gemini", category: "LLM" },
  { name: "Sentence Transformers", category: "Embeddings" },
  { name: "Docling", category: "Document Parsing" },
  { name: "NetworkX", category: "Graph Processing" },
  { name: "Cohere / Jina", category: "Reranking" },
  { name: "Langfuse", category: "Observability" },
];

const benchmarks = [
  { metric: "Recall@5", value: "92%", baseline: "66%" },
  { metric: "RAGAS Faithfulness", value: "0.87", baseline: "n/a" },
  { metric: "p95 Latency", value: "<2.5s", baseline: "5s+" },
  { metric: "Documents Ingested", value: "31-item golden set", baseline: "3 items" },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-900 py-20 lg:py-32">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-4xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
            >
              <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold text-gray-900 dark:text-white tracking-tight">
                Document Intelligence
                <span className="block text-blue-600">Powered by AI</span>
              </h1>
              <p className="mt-6 text-xl text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
                Enterprise-grade RAG platform with advanced retrieval, agentic capabilities,
                and production-ready observability. Built for teams that need answers from their documents.
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="mt-10 flex flex-col sm:flex-row gap-4 justify-center"
            >
              <Link
                href="/dashboard"
                className="inline-flex items-center justify-center px-8 py-4 text-lg font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
              >
                Get Started
                <ArrowRight className="ml-2 h-5 w-5" />
              </Link>
              <a
                href="https://github.com/himanshu-nakrani/document-qa"
                className="inline-flex items-center justify-center px-8 py-4 text-lg font-semibold text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                View on GitHub
              </a>
            </motion.div>

            {/* Stats */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.4 }}
              className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-8"
            >
              {benchmarks.map((item) => (
                <div key={item.metric} className="text-center">
                  <div className="text-3xl font-bold text-blue-600">{item.value}</div>
                  <div className="text-sm text-gray-600 dark:text-gray-400">{item.metric}</div>
                  <div className="text-xs text-gray-400">vs {item.baseline} baseline</div>
                </div>
              ))}
            </motion.div>
          </div>
        </div>

        {/* Background decoration */}
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[600px] bg-blue-400/20 rounded-full blur-3xl" />
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 lg:py-32 bg-white dark:bg-gray-900">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white">
              Everything you need for document QA
            </h2>
            <p className="mt-4 text-lg text-gray-600 dark:text-gray-300">
              From ingestion to retrieval to conversation, every component is optimized for accuracy and performance.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, index) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: index * 0.1 }}
                className="p-6 rounded-2xl bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 hover:shadow-lg transition-shadow"
              >
                <feature.icon className="h-10 w-10 text-blue-600 mb-4" />
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  {feature.title}
                </h3>
                <p className="text-gray-600 dark:text-gray-300">
                  {feature.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Architecture Section */}
      <section className="py-20 lg:py-32 bg-gray-50 dark:bg-gray-800">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-bold text-center text-gray-900 dark:text-white mb-12">
              Architecture Overview
            </h2>

            <div className="bg-white dark:bg-gray-900 rounded-2xl p-8 shadow-lg border border-gray-200 dark:border-gray-700">
              <div className="grid md:grid-cols-3 gap-6 text-center">
                <div className="p-4">
                  <Database className="h-12 w-12 text-green-600 mx-auto mb-3" />
                  <h3 className="font-semibold text-gray-900 dark:text-white">Ingestion Layer</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                    Docling extraction, OCR, semantic chunking, table detection, and GraphRAG entity extraction
                  </p>
                </div>
                <div className="p-4">
                  <Brain className="h-12 w-12 text-purple-600 mx-auto mb-3" />
                  <h3 className="font-semibold text-gray-900 dark:text-white">Retrieval Pipeline</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                    Hybrid search, reranking, MMR, query transforms, context compression, and groundedness verification
                  </p>
                </div>
                <div className="p-4">
                  <Users className="h-12 w-12 text-blue-600 mx-auto mb-3" />
                  <h3 className="font-semibold text-gray-900 dark:text-white">Application Layer</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                    Streaming chat, notebook UX, workspace RBAC, connectors, and prompt library
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tech Stack */}
      <section className="py-20 bg-white dark:bg-gray-900">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-white mb-12">
            Built with Modern Technology
          </h2>

          <div className="flex flex-wrap justify-center gap-3 max-w-4xl mx-auto">
            {techStack.map((tech) => (
              <span
                key={tech.name}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-full text-sm font-medium"
              >
                {tech.name}
                <span className="text-gray-400 ml-2 text-xs">{tech.category}</span>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 lg:py-32 bg-blue-600">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
            Ready to get started?
          </h2>
          <p className="text-xl text-blue-100 mb-10 max-w-2xl mx-auto">
            Deploy your own instance in minutes with Docker Compose, or explore the demo deployment.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center px-8 py-4 text-lg font-semibold text-blue-600 bg-white rounded-lg hover:bg-gray-100 transition-colors"
            >
              Launch App
              <ArrowRight className="ml-2 h-5 w-5" />
            </Link>
            <a
              href="/docs"
              className="inline-flex items-center justify-center px-8 py-4 text-lg font-semibold text-white border-2 border-white rounded-lg hover:bg-white/10 transition-colors"
            >
              Documentation
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-gray-900 text-gray-400">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="flex items-center gap-2 mb-4 md:mb-0">
              <FileText className="h-6 w-6 text-blue-500" />
              <span className="text-white font-semibold">Document QA</span>
            </div>
            <div className="flex gap-6">
              <a href="https://github.com/himanshu-nakrani/document-qa" className="hover:text-white transition-colors">
                GitHub
              </a>
              <a href="/docs" className="hover:text-white transition-colors">
                Docs
              </a>
              <a href="/dashboard" className="hover:text-white transition-colors">
                App
              </a>
            </div>
          </div>
          <div className="mt-8 text-center text-sm">
            Built with ❤️ by Himanshu Nakrani. Open source under MIT license.
          </div>
        </div>
      </footer>
    </div>
  );
}
