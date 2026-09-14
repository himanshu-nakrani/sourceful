## 2024-11-20 - Ensure email inputs have correct type attribute
**Learning:** For a better user experience on mobile devices and native browser validation, email inputs should use the `type="email"` attribute.
**Action:** Always check the `type` attribute of email inputs. Ensure they are set to `email` instead of defaulting to `text`.

## 2024-05-18 - Input Fields Require Explicit Types for Mobile Accessibility
**Learning:** React input components like `TextField` will default to `type="text"` unless explicitly specified. This provides a poor experience on mobile devices where specific keyboards (e.g. for URLs or emails) are highly beneficial.
**Action:** Always verify that input fields, especially those handling specific data types like URLs, have the correct `type` attribute (e.g., `type="url"`) to ensure the proper virtual keyboard is displayed and native validation triggers.

## 2024-09-12 - Preserving Visible Labels and Dynamic Counts for Screen Readers
**Learning:** Overriding visible button labels with `aria-label` on disclosure controls (e.g. "Sources: all", "Stream timeline (N events)", "Top N chunks") hides dynamic count and status details from screen reader users and can violate WCAG 2.5.3 (Label in Name). `aria-expanded` already communicates the toggle/collapsed state.
**Action:** Rely on visible text and `aria-expanded` for accessible naming on disclosure buttons with dynamic counters. For compact action buttons like "Reset to all", ensure any descriptive `aria-label` starts with the exact visible text (e.g., `aria-label="Reset to all sources"`).
