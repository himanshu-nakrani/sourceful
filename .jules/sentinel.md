## 2025-04-10 - Hardcoded Administrative Credentials
**Vulnerability:** Found hardcoded administrative email and password directly embedded in the `backend/auth.py` source file (`DEFAULT_SUPERUSER_EMAIL` / `DEFAULT_SUPERUSER_PASSWORD`).
**Learning:** Hardcoding credentials exposes sensitive information if the source code is compromised, read, or leaked.
**Prevention:** Always use environment variables combined with settings management solutions like pydantic `BaseSettings` to pass configuration to the application, falling back on safe defaults only in development.


## 2026-04-11 - Missing Chat Input Validation
**Vulnerability:** Missing length validation on user chat queries created a potential DoS vulnerability by allowing users to submit excessively long prompts to the backend LLM endpoints.
**Learning:** Long inputs can exhaust tokens and cause downstream processing (like embedding creation or LLM calls) to consume excessive API credits and processing time, or hang indefinitely.
**Prevention:** Apply a character limit (e.g., `MAX_QUESTION_LENGTH`) to user chat messages via strict Pydantic model validation and a manual early check returning a 413 Payload Too Large error.

## 2025-04-15 - Missing Admin Authorization on Analytics Endpoint
**Vulnerability:** The `/api/analytics/overview` endpoint was only enforcing `require_authenticated_context`, allowing any authenticated user to access system-wide analytics data (including user counts, signups, document metrics, etc.).
**Learning:** Endpoints returning aggregated or system-wide data must enforce role-based access control (RBAC), not just authentication. Relying solely on `Depends(require_authenticated_context)` is insufficient for admin-only functionality.
**Prevention:** Always verify that administrative and reporting endpoints use `Depends(require_admin_context)` to enforce the principle of least privilege.

## 2025-04-20 - Missing Timeout on External OAuth Token Exchange
**Vulnerability:** The Google OAuth token exchange request in `backend/routers/auth.py` lacked an explicit timeout configuration on the `httpx.AsyncClient`.
**Learning:** Unbounded network calls can hang indefinitely if the upstream service is slow or unresponsive. In asynchronous frameworks like FastAPI, this can tie up worker threads, leading to resource exhaustion and potential Denial of Service (DoS) conditions.
**Prevention:** Always configure an explicit, reasonable timeout (e.g., `timeout=10.0`) on all outbound HTTP requests made by the backend service.
## 2025-05-18 - Rate Limit Bypass in Middleware
**Vulnerability:** The rate limiter in RateLimitMiddleware combined the user's IP address with the first 24 characters of the Authorization header to form the rate limit bucket ID.
**Learning:** Because the Authorization header is client-controlled, an attacker could generate arbitrary unique bucket IDs by randomizing the Authorization header, completely bypassing the rate limits.
**Prevention:** Always use secure, trusted identifiers for rate limiting. Unauthenticated requests should be rate-limited strictly by the client IP address (or by combined IP + user agent if desired but IP is standard). Do not incorporate arbitrary untrusted client input into rate limit bucket generation.
