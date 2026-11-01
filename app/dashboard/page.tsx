"use client";

import React, { useCallback, useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import WelcomeScreen from "../components/WelcomeScreen";
import Sidebar from "../components/Sidebar";
import ChatArea from "../components/ChatArea";
import SettingsPanel from "../components/SettingsPanel";
import UploadModal from "../components/UploadModal";
import CommandPalette from "../components/CommandPalette";
import OAuthCallback from "../components/OAuthCallback";
import { ToastProvider } from "../components/Toast";
import { ServerStateProvider } from "../lib/server-state";
import { StoreProvider, useStore } from "../lib/store";
import { useKeyboardShortcuts } from "../lib/useKeyboardShortcuts";
import { ErrorBanner } from "../components/ui";

/**
 * Top-level application shell that manages global UI state, keyboard shortcuts, drag-and-drop uploads, and conditional screens.
 *
 * Renders an auth/loading view while authentication is loading, a welcome/setup screen when initial setup or API key is missing, or the main app layout containing Sidebar, ChatArea, UploadModal, and SettingsPanel. Handles opening/closing the upload modal (including receiving a dropped file), global drag-and-drop to trigger uploads, sidebar backdrop for mobile, and keyboard shortcuts for upload, settings, and escape behavior. Dispatches store actions for settings, sidebar, and setup completion.
 *
 * @returns The app's UI as a JSX element.
 */
function DashboardOAuth() {
  const { dispatch } = useStore();
  const [oauthError, setOauthError] = useState<string | null>(null);
  return (
    <>
      <OAuthCallback
        onAuthenticated={(user) => {
          dispatch({ type: "SET_CURRENT_USER", payload: user });
          dispatch({ type: "SET_SETUP_COMPLETE", payload: true });
        }}
        onError={setOauthError}
      />
      {oauthError ? (
        <div className="fixed top-3 left-1/2 z-[60] w-[min(420px,92vw)] -translate-x-1/2">
          <ErrorBanner message={oauthError} onDismiss={() => setOauthError(null)} />
        </div>
      ) : null}
    </>
  );
}

function AppShell() {
  const { state, dispatch } = useStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [dropFile, setDropFile] = useState<File | null>(null);
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);

  // Show the welcome/setup screen only for anonymous visitors who have not
  // finished setup. Authenticated users are never gated here: `setupComplete`
  // is in-memory per StoreProvider and `/login` mounts its own provider, so a
  // flag set during sign-in cannot survive the redirect into this route. They
  // land in the app and ChatArea's own "API Key Required" empty state prompts
  // for the BYOK key instead.
  const needsSetup =
    !state.currentUser && !state.setupComplete && !state.settings.providerApiKey.trim();

  const openUpload = useCallback((file?: File) => {
    if (file) setDropFile(file);
    setUploadOpen(true);
  }, []);

  const closeUpload = useCallback(() => {
    setUploadOpen(false);
    setDropFile(null);
  }, []);

  useKeyboardShortcuts({
    onUpload: () => openUpload(),
    onSettings: () => dispatch({ type: "SET_SETTINGS_OPEN", payload: true }),
    onCommandPalette: () => setCmdPaletteOpen((v) => !v),
    onEscape: () => {
      if (cmdPaletteOpen) setCmdPaletteOpen(false);
      else if (uploadOpen) closeUpload();
      else if (state.settingsOpen) dispatch({ type: "SET_SETTINGS_OPEN", payload: false });
      else if (window.matchMedia("(max-width: 767px)").matches) {
        dispatch({ type: "SET_SIDEBAR", payload: false });
      }
    },
  });

  if (state.authLoading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: "var(--bg-primary)" }}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25 }}
          className="flex items-center gap-3 px-6 py-5"
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-xl)",
            boxShadow: "var(--shadow-xs)",
          }}
        >
          <Loader2
            size={16}
            className="animate-spin"
            style={{ color: "var(--accent-secondary)" }}
          />
          <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
            Loading
          </span>
        </motion.div>
      </div>
    );
  }

  if (needsSetup) {
    return <WelcomeScreen onComplete={() => dispatch({ type: "SET_SETUP_COMPLETE", payload: true })} />;
  }

  const handleGlobalDrop = (event: React.DragEvent) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) openUpload(file);
  };

  return (
    <div
      className="flex h-[100dvh] overflow-hidden relative w-full"
      style={{ background: "var(--bg-primary)" }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleGlobalDrop}
    >
      {state.sidebarOpen && (
        <motion.button
          type="button"
          className="fixed inset-0 z-30 md:hidden cursor-default"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={() => dispatch({ type: "SET_SIDEBAR", payload: false })}
          aria-label="Close sidebar"
          style={{ background: "rgba(4, 6, 9, 0.55)" }}
        />
      )}
      <Sidebar onUploadClick={() => openUpload()} />
      <ChatArea onUploadClick={() => openUpload()} />
      <UploadModal open={uploadOpen} onClose={closeUpload} initialFile={dropFile} />
      <SettingsPanel
        open={state.settingsOpen}
        onClose={() => dispatch({ type: "SET_SETTINGS_OPEN", payload: false })}
      />
      <CommandPalette
        open={cmdPaletteOpen}
        onClose={() => setCmdPaletteOpen(false)}
        onUpload={() => openUpload()}
        onSettings={() => dispatch({ type: "SET_SETTINGS_OPEN", payload: true })}
      />
    </div>
  );
}

export default function Home() {
  return (
    <StoreProvider>
      <DashboardOAuth />
      <ServerStateProvider>
        <ToastProvider>
          <AppShell />
        </ToastProvider>
      </ServerStateProvider>
    </StoreProvider>
  );
}
