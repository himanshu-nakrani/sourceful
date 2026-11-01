"use client";

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Check, FileText, Quote, ShieldCheck } from "lucide-react";
import type { AuthUser } from "../lib/api";
import { EASE_OUT } from "../lib/motion";
import { useStore } from "../lib/store";
import AuthForm from "./AuthForm";
import Brand from "./Brand";

export default function AuthScreen() {
  const { dispatch } = useStore();
  const handleAuthenticated = React.useCallback((user: AuthUser) => {
    dispatch({ type: "SET_CURRENT_USER", payload: user });
  }, [dispatch]);

  return (
    <main className="grid min-h-[100dvh] lg:grid-cols-2" style={{ background: "var(--bg-surface)" }}>
      <section className="flex flex-col px-7 py-8 sm:px-12 lg:min-h-[100dvh] lg:px-14 lg:py-10 xl:px-20" style={{ background: "var(--bg-secondary)" }}>
        <Brand />
        <motion.div
          className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center py-12 lg:py-16"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: EASE_OUT }}
        >
          <p className="mb-5 text-xs font-medium tracking-[0.12em]" style={{ color: "var(--accent-primary)" }}>A LITTLE LESS SEARCHING. A LOT MORE CLARITY.</p>
          <h1 className="text-[38px] font-semibold leading-[1.12] tracking-[-0.045em] sm:text-5xl xl:text-[56px]" style={{ color: "var(--text-primary)" }}>
            Your documents.<br /><span style={{ color: "var(--accent-primary)" }}>A clearer perspective.</span>
          </h1>
          <p className="mt-6 max-w-[390px] text-[15px] leading-7" style={{ color: "var(--text-secondary)" }}>
            Turn scattered information into answers you can trust. Ask, explore, and trace every insight back to its source.
          </p>
          <div className="mt-10 hidden sm:block" aria-label="Illustrative example of a cited answer">
            <div className="rounded-2xl p-5 sm:p-6" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow-md)" }}>
              <div className="flex items-center gap-3 pb-4" style={{ borderBottom: "1px solid var(--border)" }}>
                <span className="flex h-10 w-9 items-center justify-center rounded-lg" style={{ background: "var(--accent-primary-soft)", color: "var(--accent-primary)" }}><FileText size={19} strokeWidth={1.5} /></span>
                <div className="min-w-0 flex-1"><p className="text-[13px] font-medium" style={{ color: "var(--text-primary)" }}>Product strategy.pdf</p><p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>Ready to explore</p></div>
                <Check size={15} style={{ color: "var(--accent-primary)" }} />
              </div>
              <p className="mt-5 text-[13px] font-medium" style={{ color: "var(--text-primary)" }}>What are the team’s top priorities?</p>
              <p className="mt-2 text-[13px] leading-6" style={{ color: "var(--text-secondary)" }}>Focus the roadmap, talk to customers, and measure what matters.</p>
              <span className="mt-4 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium" style={{ background: "var(--accent-primary-soft)", color: "var(--accent-primary)" }}><Quote size={11} /> Product strategy · p. 4</span>
            </div>
            <p className="mt-3 text-center text-[11px]" style={{ color: "var(--text-muted)" }}>A glimpse of your workspace · illustrative example</p>
          </div>
        </motion.div>
        <p className="hidden items-center gap-2 text-xs sm:flex" style={{ color: "var(--text-tertiary)" }}><ShieldCheck size={14} /> Self-hosted. Your models. Your control.</p>
      </section>
      <section className="flex flex-col items-center justify-center px-6 py-12 sm:px-12 lg:py-20" aria-label="Sign in to Sourceful">
        <div className="w-full max-w-[380px]">
          <AuthForm onAuthenticated={handleAuthenticated} />
          <div className="mt-8 pt-6 text-center" style={{ borderTop: "1px solid var(--border)" }}>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>Prefer to try it on your own?</p>
            <Link href="/dashboard" className="focus-ring mt-3 inline-flex items-center gap-2 rounded-md text-[13px] font-medium transition-colors hover:underline underline-offset-4" style={{ color: "var(--accent-primary)" }}>Continue without an account <ArrowRight size={14} /></Link>
            <p className="mt-2 text-[11px] leading-5" style={{ color: "var(--text-muted)" }}>Bring your own API key. Your session stays separate.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
