## 2025-04-10 - Hardcoded Administrative Credentials
**Vulnerability:** Found hardcoded administrative email and password directly embedded in the `backend/auth.py` source file (`DEFAULT_SUPERUSER_EMAIL` / `DEFAULT_SUPERUSER_PASSWORD`).
**Learning:** Hardcoding credentials exposes sensitive information if the source code is compromised, read, or leaked.
**Prevention:** Always use environment variables combined with settings management solutions like pydantic `BaseSettings` to pass configuration to the application, falling back on safe defaults only in development.
## 2025-02-28 - Missing Security Headers Mitigation
**Vulnerability:** The FastAPI backend did not set standard HTTP security headers on its responses, exposing the application to potential risks like clickjacking, MIME-sniffing, and certain types of XSS attacks.
**Learning:** Security headers are not configured by default in FastAPI. This required an explicit middleware to be injected into the application pipeline to automatically append these headers across all routes.
**Prevention:** Always implement a dedicated middleware (like `SecurityHeadersMiddleware`) early in the application stack to ensure uniform security header enforcement (`X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `X-XSS-Protection`) for all outward-facing API endpoints.
