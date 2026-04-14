"use client";

import { useEffect } from "react";

interface ShortcutHandlers {
  onUpload: () => void;
  onSettings: () => void;
  onEscape: () => void;
}

/**
 * Registers global keyboard shortcuts for upload, settings, and escape actions.
 *
 * Subscribes to window keydown events and invokes the provided handlers when their
 * corresponding keys are pressed: Escape always triggers `onEscape`; Meta/Ctrl+U (case-insensitive)
 * triggers `onUpload`; Meta/Ctrl+, triggers `onSettings`. Shortcut keys are ignored when focus
 * is inside `input`, `textarea`, or `select` elements.
 *
 * @param onUpload - Callback invoked when the upload shortcut (Meta/Ctrl+U) is triggered
 * @param onSettings - Callback invoked when the settings shortcut (Meta/Ctrl+,) is triggered
 * @param onEscape - Callback invoked when the Escape key is pressed
 */
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
