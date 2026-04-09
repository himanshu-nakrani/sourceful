## 2024-05-15 - Missing ARIA labels on Icon-only Buttons
**Learning:** Found a common pattern in the application where icon-only buttons (like refresh, close, edit, delete) in `Sidebar.tsx` and `UploadModal.tsx` are missing `aria-label` and `title` attributes, making them completely inaccessible to screen readers and difficult to understand without tooltips.
**Action:** Always verify that buttons containing only icons include descriptive `aria-label` and `title` props for accessibility and usability.
