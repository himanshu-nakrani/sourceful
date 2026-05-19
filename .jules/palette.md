## 2024-05-19 - WorkspaceNotesPanel Accessibility
**Learning:** Found that inputs and textareas that rely on placeholders without labels were inaccessible, and the icon-only trash button lacked context. The same applies across many components in the application.
**Action:** Ensure that all inputs, textareas, and icon-only buttons receive `aria-label`s or associated `<label>`s to remain accessible to screen readers.
