## 2025-04-10 - Hardcoded Administrative Credentials
**Vulnerability:** Found hardcoded administrative email and password directly embedded in the `backend/auth.py` source file (`DEFAULT_SUPERUSER_EMAIL` / `DEFAULT_SUPERUSER_PASSWORD`).
**Learning:** Hardcoding credentials exposes sensitive information if the source code is compromised, read, or leaked.
**Prevention:** Always use environment variables combined with settings management solutions like pydantic `BaseSettings` to pass configuration to the application, falling back on safe defaults only in development.
