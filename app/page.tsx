"use client";

import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import AuthScreen from "./components/AuthScreen";
import InsightsDashboard from "./components/InsightsDashboard";
import UserManagement from "./components/UserManagement";
import ModelManagement from "./components/ModelManagement";
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
      <div className="flex min-h-screen items-center justify-center gap-3" style={{ background: "var(--bg-primary)", color: "var(--text-secondary)" }}>
        {/* [layout] Added spinner to loading state for visual feedback */}
        <Loader2 size={20} className="animate-spin" />
        Loading workspace...
      </div>
    );
  }

  if (!state.currentUser) {
    return <AuthScreen />;
  }

  const renderContent = () => {
    switch (state.activeView) {
      case "insights":
        return <InsightsDashboard />;
      case "users":
        return <UserManagement />;
      case "models":
        return <ModelManagement />;
      default:
        return <ChatArea onUploadClick={() => setUploadOpen(true)} />;
    }
  };

  return (
    <div className="flex h-[100dvh] overflow-hidden relative w-full" style={{ background: "var(--bg-primary)" }}>
      {state.sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 md:hidden transition-opacity"
          onClick={() => dispatch({ type: "SET_SIDEBAR", payload: false })}
        />
      )}
      <Sidebar onUploadClick={() => setUploadOpen(true)} />
      {renderContent()}
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
