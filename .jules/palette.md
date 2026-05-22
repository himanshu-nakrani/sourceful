## 2024-05-19 - WorkspaceNotesPanel Accessibility
**Learning:** Found that inputs and textareas that rely on placeholders without labels were inaccessible, and the icon-only trash button lacked context. The same applies across many components in the application.
**Action:** Ensure that all inputs, textareas, and icon-only buttons receive `aria-label`s or associated `<label>`s to remain accessible to screen readers.
## 2024-05-22 - Add aria-labels to inputs lacking explicit labels
**Learning:** Found several `<input>` elements in `ModelManagement.tsx` and `WelcomeScreen.tsx` that relied solely on `placeholder` attributes without an associated `<label>` or an `aria-label`. This makes it difficult for screen readers to convey the purpose of the input.
**Action:** Adding `aria-label` attributes to these inputs improves keyboard/screen-reader accessibility and is a quick, safe micro-UX improvement that aligns with WCAG best practices.
