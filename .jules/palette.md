## 2024-04-12 - Added native form validation
**Learning:** Native HTML5 validation (`required`) provides an excellent, accessible fallback for form validation before complex state-based validation is triggered.
**Action:** Always check form inputs for basic HTML5 validation attributes (`required`, `type="email"`, `minLength`, etc.) before implementing custom JavaScript validation logic.
## 2024-04-12 - Added focus rings to custom inputs
**Learning:** Tailwind CSS resets input styles, including focus rings. Using `outline-none` removes accessibility focus indicators for keyboard navigation.
**Action:** Replace `outline-none` with `focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:outline-none` to ensure keyboard users have clear focus indicators while maintaining the intended visual design.
## 2026-04-15 - Consistent Keyboard Focus Indicators for Buttons
**Learning:** While inputs had consistent focus rings, interactive buttons (like those on the AuthScreen) relied on default browser outlines which were inconsistent or hidden due to existing styles.
**Action:** Ensure all interactive elements, especially primary buttons, include `outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]` to provide a clear and accessible visual indicator for keyboard users.
## 2026-04-19 - Added proper ID linking for form accessibility
**Learning:** Screen readers and keyboard users rely heavily on the explicit relationship between a label and an input, which is established using the 'id' and 'htmlFor' attributes. React's 'useId()' hook simplifies this process significantly without generating conflicts in components that appear multiple times.
**Action:** When creating reusable form components, immediately assign `const id = React.useId()` and link the `label htmlFor={id}` and `input id={id}` for full accessibility support.

## 2026-04-20 - aria-expanded on toggle buttons
**Learning:** When building collapsible UI sections or accordions, setting the `aria-expanded` attribute on the toggle button is essential for screen reader users to understand the current state and predict the action of the button.
**Action:** Always bind the `aria-expanded` attribute to the boolean state tracking the visibility of the corresponding collapsible content section.
