"use client";

import React, { useCallback, useState } from "react";
import { Loader2 } from "lucide-react";
import WelcomeScreen from "./components/WelcomeScreen";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import SettingsPanel from "./components/SettingsPanel";
import UploadModal from "./components/UploadModal";
import { ServerStateProvider } from "./lib/server-state";
import { StoreProvider, useStore } from "./lib/store";
import { useKeyboardShortcuts } from "./lib/useKeyboardShortcuts";

/**
 * Top-level application shell that manages global UI state, keyboard shortcuts, drag-and-drop uploads, and conditional screens.
 *
 * Renders an auth/loading view while authentication is loading, a welcome/setup screen when initial setup or API key is missing, or the main app layout containing Sidebar, ChatArea, UploadModal, and SettingsPanel. Handles opening/closing the upload modal (including receiving a dropped file), global drag-and-drop to trigger uploads, sidebar backdrop for mobile, and keyboard shortcuts for upload, settings, and escape behavior. Dispatches store actions for settings, sidebar, and setup completion.
 *
 * @returns The app's UI as a JSX element.
 */
function AppShell() {
  const { state, dispatch } = useStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [dropFile, setDropFile] = useState<File | null>(null);

  // Show welcome screen if setup not complete and no API key
  const needsSetup = !state.setupComplete && !state.settings.providerApiKey.trim();

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
    onEscape: () => {
      if (uploadOpen) closeUpload();
      else dispatch({ type: "SET_SETTINGS_OPEN", payload: false });
    },
  });

  if (state.authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3" style={{ background: "var(--bg-primary)", color: "var(--text-secondary)" }}>
        <Loader2 size={20} className="animate-spin" />
        Loading...
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
        <div
          className="fixed inset-0 bg-black/50 z-30 md:hidden transition-opacity"
          onClick={() => dispatch({ type: "SET_SIDEBAR", payload: false })}
        />
      )}
      <Sidebar onUploadClick={() => openUpload()} />
      <ChatArea onUploadClick={() => openUpload()} />
      <UploadModal open={uploadOpen} onClose={closeUpload} initialFile={dropFile} />
      <SettingsPanel
        open={state.settingsOpen}
        onClose={() => dispatch({ type: "SET_SETTINGS_OPEN", payload: false })}
      />
    </div>
  );
}

export default function Home() {
  return (
    <StoreProvider>
      <ServerStateProvider>
        <AppShell />
      </ServerStateProvider>
    </StoreProvider>
  );
}
