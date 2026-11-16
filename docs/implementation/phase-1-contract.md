# Phase 1 contract

Implement foundation and email OTP login only. Future trips/search/chat are not implemented.

API prefix `/api/v1`. All calls use same-origin credentials. Errors: `{ "detail": "Traditional Chinese message" }`.
- POST `/auth/request-code` `{email}`: 202 `{message, retry_after:60}`. Generic response even for disallowed emails. 429 when throttled, 503 SMTP unavailable.
- POST `/auth/verify-code` `{email,code}`: 200 `{user:{id,email},csrf_token}` and HttpOnly session cookie. 401 invalid/expired code.
- GET `/auth/me`: 200 `{user:{id,email},csrf_token}` or 401.
- POST `/auth/logout`: requires `X-CSRF-Token`, returns 204; clears cookie.
- GET `/health/live`: `{status:"ok"}`.
- GET `/health/ready`: 200/503 `{status:"ready"|"not_ready",database:boolean,smtp_configured:boolean}`. No network email test.

Frontend Vue 3 TypeScript Vite. Port 5173 proxy `/api` to localhost:8000. No password field. Email then six-digit OTP, resend countdown, errors, loading, return to email, refresh session on page load, signed-in welcome with email and logout. Clearly state that journey management comes next; no fake feature buttons. Keep CSRF token in memory. No secrets or auth tokens in localStorage.

Design: travel notebook, pale blue #edf5f7, paper #ffffff, ink #153e48, teal #176b68, yellow #e8c768; system Chinese sans and Georgia for Latin TravelMemo wordmark. Left-aligned two-column desktop with simple route-line motif; single-column phone. Accessible labels, autofocus OTP after success, polite status, visible focus, reduced motion, 44px controls. No remote fonts/images.
