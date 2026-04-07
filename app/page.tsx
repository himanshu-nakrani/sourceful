"use client";

import React, { useState } from "react";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import SettingsPanel from "./components/SettingsPanel";
import UploadModal from "./components/UploadModal";
import { ServerStateProvider } from "./lib/server-state";
import { StoreProvider, useStore } from "./lib/store";

function AppShell() {
  const { state, dispatch } = useStore();
  const [uploadOpen, setUploadOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--bg-primary)" }}>
      <Sidebar onUploadClick={() => setUploadOpen(true)} />
      <ChatArea onUploadClick={() => setUploadOpen(true)} />
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
