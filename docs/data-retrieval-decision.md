# ADR: request-driven stock data retrieval (S5)

Status: implemented; live entitlement not yet configured. Decision date: November 11, 2026.

Users supply stock symbol(s) and dates through the documented API. There is no fixed company list. Retrieve Alpha Vantage TIME_SERIES_DAILY closes on demand for that request, using environment credentials and the selected exchange calendar. Full history supports arbitrary one-year intervals when the account is entitled; compact is limited to its latest 100 observations.

No shared database, persistent stock store or background bulk-download job is required for the current service. No cross-service cache is introduced. This keeps the service independently deployable and avoids silently serving stale data. Repeated requests consume quota; source errors are explicit rather than fabricated successful values. Timeout policy: 12-second shared lookup wait budget plus per-call socket timeouts.

Alternatives considered: shared S1 dependency (rejected because other services must survive S1 removal); persistent preloading (deferred until a provider entitlement and exact run are available); response caching (deferred until freshness, ownership and quota policy are agreed). This decision completes the per-service retrieval-policy implementation portion of task 4.07, not the team's final shared data strategy.

The existing core/source tests validate coverage, invalid prices, limits, errors and recovery with fixed/fake responses. That evidence completes task 4.06's local implementation/testing portion. It does not complete live-access confirmation (4.04), actual one-year retrieval (4.05), or live completeness/correctness verification (4.08). The user confirms no Alpha Vantage key has been configured. These tasks remain pending with a concrete setup path in the README.
