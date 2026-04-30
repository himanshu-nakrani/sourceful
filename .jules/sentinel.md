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

## 2025-04-26 - [CRITICAL] Server-Side Request Forgery (SSRF) in URL Ingest
**Vulnerability:** The application allowed users to provide arbitrary URLs for ingestion, which were directly fetched by `httpx.AsyncClient` without validating the resolved IP address. This allowed users to bypass network perimeters and access internal network resources (e.g., `localhost`, loopback, and metadata services like AWS EC2 instance metadata `169.254.169.254`).
**Learning:** Checking the URL string is insufficient because attackers can use DNS rebinding or direct IP addresses. We must resolve the hostname to an IP address at the moment of request and block restricted ranges.
**Prevention:** Always validate resolved IP addresses for external fetching services. Using an `event_hook` on the HTTP client (`httpx.AsyncClient`) provides a clean point to interrupt requests to private, loopback, link-local, or multicast addresses right before the connection is made.
## 2025-04-28 - [CRITICAL] Server-Side Request Forgery (SSRF) in UrlSourceAdapter
**Vulnerability:** The `UrlSourceAdapter` in `backend/connectors/adapter.py` fetched arbitrary URLs provided by users via `httpx.AsyncClient` without validating the resolved IP addresses. This could allow an attacker to bypass network perimeters and probe internal network resources (e.g., `localhost`, loopback, or private IP ranges).
**Learning:** Checking the URL string is not enough to prevent SSRF. Attackers can use DNS rebinding or direct IP addresses. It's critical to resolve the hostname to an IP address at the moment of request and block restricted ranges.
**Prevention:** Always validate resolved IP addresses for external fetching services. Using an `event_hook` on the HTTP client (`httpx.AsyncClient`) with `ipaddress` provides a reliable way to interrupt requests to private, loopback, link-local, or multicast addresses right before the connection is established.

## 2025-04-29 - [CRITICAL] Refactoring SSRF Protection
**Vulnerability:** The SSRF protection hook was duplicated across multiple connector files. In addition, there was a risk of breaking integrations like Confluence that might genuinely be hosted on private internal networks.
**Learning:** Security protections should be centralized in a utility module to avoid code duplication and ensure consistent enforcement across the codebase. Applying strict SSRF rules (blocking private IPs) on connectors that might validly point to on-premise servers (like Jira/Confluence) requires careful consideration and potentially different risk models, although here it was applied universally per the current requirements.
**Prevention:** Always extract common security hooks (like `prevent_ssrf_hook`) into a central `backend/utils/network.py` or similar location.
## 2025-05-01 - [CRITICAL] Refactoring SSRF Protection
**Vulnerability:** The SSRF protection hook was missing from the Confluence and Notion connectors, which fetch content from user-provided URLs/spaces. Furthermore, aggressively modifying external timeouts from 30 seconds to 10 seconds across all endpoints without considering the inherent slowness of specific external APIs (like Notion/Confluence) introduces regression risks.
**Learning:** Security protections like `get_ssrf_event_hooks()` should be consistently applied to all `httpx.AsyncClient` instances that interact with user-configurable external systems. However, security fixes should remain tightly scoped. Sweeping stylistic changes (like running codebase-wide formatters) or aggressive timeout reductions should not be bundled with targeted security patches to ensure the fix is reviewable and safe.
**Prevention:** Always scope security fixes to the exact lines necessary to mitigate the vulnerability. Ensure any default timeouts respect the expected response times of the external APIs being called.
