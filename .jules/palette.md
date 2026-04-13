## 2024-04-12 - Added native form validation
**Learning:** Native HTML5 validation (`required`) provides an excellent, accessible fallback for form validation before complex state-based validation is triggered.
**Action:** Always check form inputs for basic HTML5 validation attributes (`required`, `type="email"`, `minLength`, etc.) before implementing custom JavaScript validation logic.
## 2024-04-12 - Added focus rings to custom inputs
**Learning:** Tailwind CSS resets input styles, including focus rings. Using `outline-none` removes accessibility focus indicators for keyboard navigation.
**Action:** Replace `outline-none` with `focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:outline-none` to ensure keyboard users have clear focus indicators while maintaining the intended visual design.
