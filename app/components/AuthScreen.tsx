\"use client\";

import React from \"react\";
import Link from \"next/link\";
import { ArrowRight } from \"lucide-react\";
import type { AuthUser } from \"../lib/api\";
import { useStore } from \"../lib/store\";
import AuthForm from \"./AuthForm\";
import Brand from \"./Brand\";

export default function AuthScreen() {
  const { dispatch } = useStore();
  const handleAuthenticated = React.useCallback((user: AuthUser) => {
    dispatch({ type: \"SET_CURRENT_USER\", payload: user });
  }, [dispatch]);

  return (
    <main
      className=\"flex min-h-[100dvh] flex-col lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(390px,0.85fr)]\"
      style={{ background: \"var(--bg-surface)\" }}
    >
      <section
        className=\"flex flex-col border-b px-6 py-5 sm:px-8 lg:min-h-[100dvh] lg:border-b-0 lg:border-r lg:px-12 lg:py-8 xl:px-16\"
        style={{ background: \"var(--bg-secondary)\", borderColor: \"var(--border)\" }}
        aria-label=\"Document research\"
      >
        <div className=\"flex items-center justify-between gap-4\">
          <Brand />
          <span
            className=\"hidden text-[11px] font-medium tracking-[0.12em] sm:block\"
            style={{ color: \"var(--text-tertiary)\" }}
          >
            Document research
          </span>
        </div>

        <div className=\"mx-auto hidden w-full max-w-[590px] flex-1 flex-col justify-center py-12 lg:flex\">
          <h1
            className=\"text-[48px] leading-[1.02] tracking-[-0.04em] xl:text-[60px]\"
            style={{ color: \"var(--text-primary)\", fontFamily: \"var(--font-editorial), Georgia, serif\" }}
          >
            Read closely.<br />
            <span style={{ color: \"var(--accent-primary)\" }}>Find the answer.</span>
          </h1>
          <p
            className=\"mt-5 max-w-[430px] text-[15px] leading-7\"
            style={{ color: \"var(--text-secondary)\" }}
          >
            Ask a question across your documents, then inspect the passage behind the answer.
          </p>

          <figure
            className=\"mt-10 w-full max-w-[560px] border-y py-4\"
            style={{ borderColor: \"var(--border)\" }}
            aria-label=\"Illustrative document answer example\"
          >
            <figcaption
              className=\"flex items-center justify-between pb-3 text-[10px] font-medium uppercase tracking-[0.14em]\"
              style={{ color: \"var(--text-muted)\" }}
            >
              <span>Illustrative example</span>
              <span>01 / 01</span>
            </figcaption>
            <dl className=\"text-[13px]\">
              <div
                className=\"grid grid-cols-[82px_minmax(0,1fr)] gap-4 border-t py-3\"
                style={{ borderColor: \"var(--border)\" }}
              >
                <dt className=\"text-[10px] font-medium tracking-[0.12em]\" style={{ color: \"var(--text-muted)\" }}>DOCUMENT</dt>
                <dd style={{ color: \"var(--text-primary)\" }}>Onboarding interview notes</dd>
              </div>
              <div
                className=\"grid grid-cols-[82px_minmax(0,1fr)] gap-4 border-t py-3\"
                style={{ borderColor: \"var(--border)\" }}
              >
                <dt className=\"text-[10px] font-medium tracking-[0.12em]\" style={{ color: \"var(--text-muted)\" }}>QUESTION</dt>
                <dd style={{ color: \"var(--text-primary)\" }}>Where did participants hesitate?</dd>
              </div>
              <div
                className=\"grid grid-cols-[82px_minmax(0,1fr)] gap-4 border-t py-3\"
                style={{ borderColor: \"var(--border)\" }}
              >
                <dt className=\"text-[10px] font-medium tracking-[0.12em]\" style={{ color: \"var(--text-muted)\" }}>ANSWER</dt>
                <dd style={{ color: \"var(--text-primary)\" }}>People struggled to find the first saved view.</dd>
              </div>
              <div
                className=\"grid grid-cols-[82px_minmax(0,1fr)] gap-4 border-t pt-3\"
                style={{ borderColor: \"var(--border)\" }}
              >
                <dt className=\"text-[10px] font-medium tracking-[0.12em]\" style={{ color: \"var(--text-muted)\" }}>SOURCE</dt>
                <dd style={{ color: \"var(--text-secondary)\" }}>
                  “The first saved view was difficult to find.”
                  <span className=\"mt-1 block text-[11px]\" style={{ color: \"var(--text-muted)\" }}>Interview 02 · page 3</span>
                </dd>
              </div>
            </dl>
          </figure>
        </div>

        <p className=\"hidden pt-6 text-[11px] lg:block\" style={{ color: \"var(--text-tertiary)\" }}>
          Answers link back to their cited passages.
        </p>
      </section>

      <section
        className=\"flex flex-1 items-center justify-center px-6 py-10 sm:px-10 lg:min-h-[100dvh] lg:px-12 lg:py-16\"
        aria-label=\"Account access\"
      >
        <div className=\"w-full max-w-[390px]\">
          <AuthForm onAuthenticated={handleAuthenticated} />
          <div className=\"mt-8 border-t pt-5\" style={{ borderColor: \"var(--border)\" }}>
            <p className=\"text-[13px]\" style={{ color: \"var(--text-secondary)\" }}>
              Or use the app without an account.
            </p>
            <Link
              href=\"/dashboard\"
              className=\"focus-ring mt-2 inline-flex items-center gap-2 rounded-[6px] text-[13px] font-medium underline-offset-4 hover:underline\"
              style={{ color: \"var(--accent-primary)\" }}
            >
              Continue without an account <ArrowRight size={14} aria-hidden=\"true\" />
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
