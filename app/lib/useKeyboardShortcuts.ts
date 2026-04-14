"use client";

import { useEffect } from "react";

interface ShortcutHandlers {
  onUpload: () => void;
  onSettings: () => void;
  onEscape: () => void;
}

export function useKeyboardShortcuts({ onUpload, onSettings, onEscape }: ShortcutHandlers) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const meta = event.metaKey || event.ctrlKey;
      const tag = (event.target as HTMLElement)?.tagName;
      const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if (event.key === "Escape") {
        onEscape();
        return;
      }

      if (meta && !isInput) {
        if (event.key === "u" || event.key === "U") {
          event.preventDefault();
          onUpload();
        } else if (event.key === ",") {
          event.preventDefault();
          onSettings();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onUpload, onSettings, onEscape]);
}
