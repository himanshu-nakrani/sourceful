"use client";

import React, { useState } from "react";
import AuthScreen from "./components/AuthScreen";
import InsightsDashboard from "./components/InsightsDashboard";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import SettingsPanel from "./components/SettingsPanel";
import UploadModal from "./components/UploadModal";
import { ServerStateProvider } from "./lib/server-state";
import { StoreProvider, useStore } from "./lib/store";

function AppShell() {
  const { state, dispatch } = useStore();
  const [uploadOpen, setUploadOpen] = useState(false);

  if (state.authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)", color: "var(--text-secondary)" }}>
        Loading workspace...
      </div>
    );
  }

  if (!state.currentUser) {
    return <AuthScreen />;
  }

  return (
    <div className="flex h-screen overflow-hidden relative w-full" style={{ background: "var(--bg-primary)" }}>
      {state.sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 md:hidden transition-opacity"
          onClick={() => dispatch({ type: "SET_SIDEBAR", payload: false })}
        />
      )}
      <Sidebar onUploadClick={() => setUploadOpen(true)} />
      {state.activeView === "dashboard" ? (
        <InsightsDashboard />
      ) : (
        <ChatArea onUploadClick={() => setUploadOpen(true)} />
      )}
      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
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
