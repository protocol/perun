# Next.js App Router footguns

Read this when `next` is a dependency (probe: `grep '"next"' package.json`) and the code uses the App Router (`app/`).

- **Every `"use server"` export is a public POST endpoint**, callable with arbitrary arguments regardless of where it
  is imported. The auth and authorization guard must be the first statement in the action, and inputs must be
  validated inside it. A guard only in the calling component or layout is not a guard.
- **`cookies().set` during render throws.** Cookies can be written only in server actions and route handlers
  (and middleware/proxy). A set in a Server Component or layout is a runtime error on that path.
- **React `cache()` is per request**, not a cross-request cache; do not rely on it for rate limiting, memoizing
  secrets, or sharing data between users. Cross-request caching is `unstable_cache` / `use cache` with explicit keys
  and tags, and must never cache per-user data under a shared key.
- **`redirect()` and `notFound()` work by throwing.** Inside `try/catch` the catch swallows them; rethrow, or call
  them outside the `try`.
- **A page that suspends (Suspense) on slow data is cut by the proxy or platform timeout** and can render blank or partial with a
  200; bound each fetch with a timeout and give the boundary a fallback error state. See the latency-budget probe in
  `reliability-error-handling.md`.
- **Server actions run serially per page.** Next queues them one at a time per client, so a slow action blocks every
  later one. List actions called on mount or from an effect, and any action that can run over ~2s (external calls,
  heavy queries); behind an optimistic UI the user sees success and the write is lost or late. Move slow work to a
  route handler or background job.
- **Enumerate every non-void server-action return**, including `boolean` and `string`. Each return value, and each
  thrown error, is serialized to the browser: a `true`/`false` can be an existence or permission oracle, a string can
  carry an internal message or id. Check the caller handles every branch rather than only the happy one.
