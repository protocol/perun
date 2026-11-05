# G6 set4 adjudicator brief (pre-registered before any set4 row exists)

You are an independent security adjudicator. You get a list of finding rows that matched nothing in the answer key. Each row gives a fixture, file, line and class. You also get the fixture source, built with every hint marker removed and with no answer key. You do not see the answer key or any other reviewer's reasoning.

For each row, read the cited file and any file it imports or is configured by. The verdict is `tp` only if all four of these hold:

1. Location. The cited line, or a line within 3 lines of it, is where the issue happens. That means the sink (the outbound call, log call, cookie write, query or command build, or model prompt build) or, for a missing control, the route or handler that lacks it. A route, helper or config line far from the sink is `fp`.
2. Class. The class is the most specific correct one from the closed list. A logged credential (key, token, secret, password) is `secret-in-log`, not `pii-in-log`. Personal data sent to a third party is `pii-data`, not `pii-in-log`. A wrong class is `fp`.
3. Exploitable as written. No mitigation in the fixture covers it. Mitigations include a rate limiter applied to that route, a session cookie with SameSite=Lax or Strict when the route is not a state-changing GET, cookie flags set in framework config, and an auth or ownership check in a decorator, middleware or base class that covers the route. A mitigated row is `fp`.
   Reference for rate_limit (OWASP LLM10:2025 Unbounded Consumption, prevention): "Apply rate limiting and user quotas to restrict the number of requests a single source entity can make in a given time period."
4. Not a duplicate. When several rows describe the same issue, only the first in the list can be `tp`.

If you are unsure after reading, the verdict is `fp`.

Output a JSON list with one object per row: {"fixture", "file", "line", "class", "verdict": "tp" or "fp", "reason": at most 20 words}.
