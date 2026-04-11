## 2025-04-10 - Hardcoded Administrative Credentials
**Vulnerability:** Found hardcoded administrative email and password directly embedded in the `backend/auth.py` source file (`DEFAULT_SUPERUSER_EMAIL` / `DEFAULT_SUPERUSER_PASSWORD`).
**Learning:** Hardcoding credentials exposes sensitive information if the source code is compromised, read, or leaked.
**Prevention:** Always use environment variables combined with settings management solutions like pydantic `BaseSettings` to pass configuration to the application, falling back on safe defaults only in development.

## 2026-04-11 - Missing Chat Input Validation
**Vulnerability:** Missing length validation on user chat queries created a potential DoS vulnerability by allowing users to submit excessively long prompts to the backend LLM endpoints.
**Learning:** Long inputs can exhaust tokens and cause downstream processing (like embedding creation or LLM calls) to consume excessive API credits and processing time, or hang indefinitely.
**Prevention:** Apply a character limit (e.g., `MAX_QUESTION_LENGTH`) to user chat messages via strict Pydantic model validation and a manual early check returning a 413 Payload Too Large error.
