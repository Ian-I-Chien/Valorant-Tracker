# Startup-only API key pool

`API_KEYS` is parsed after dotenv loading when the API module initializes. There
is no file watcher or live reload. Existing single-key installations retain
`API_KEY` compatibility. Distinct keys must have independent authorized quotas.

Each key stores an ordinal label, a secret excluded from repr, local request
timestamps, an in-flight flag, disabled/cooldown state, and the last advertised
limit/remaining quota/reset deadline. Credentials never enter cache keys or logs.

Acquisition scans round-robin under an asyncio condition and atomically reserves
the request's budget and key. Busy, disabled, cooling, or exhausted keys are
skipped. Waiting releases the condition lock; lease exit (including cancellation)
releases the in-flight slot. Reservations are conservatively charged even if
the request subsequently fails. The local limit is capped by a smaller server
limit. Serializing a key's requests prevents out-of-order quota headers from
overstating its remaining budget. The entire pool is process-local.

HTTP 401 disables only that key. HTTP 429 is treated as personal only when
`x-ratelimit-remaining` equals zero; otherwise it applies a pool-wide pause.
HTTP 403 is not automatically classified as an invalid key, because Henrik
documents maintenance/bot-prevention causes. No credential rotation happens for
403, ambiguous/global 429, network failures, or server errors.

`Retry-After` supports seconds and HTTP dates. Numeric `x-ratelimit-reset` accepts
delta seconds or Unix epoch seconds (values greater than 1,000,000,000). Invalid
or absent values default to a conservative local window; no extra quota endpoint
is called. Network/5xx failures increase the shared backoff exponentially,
2–60 seconds; advertised retry delays can extend it. Subsequent queries retry
after that backoff rather than immediately trying every key.

The API wrapper bounds key failover to three attempts and all work to 30 seconds.
Individual pool waits are bounded to five seconds and HTTP timeouts remain
connect=8/total=20 seconds. Existing response caching and stale fallback surround
the pool, so requests served from cache consume no key quota. Interactive command
error handlers provide a retry-later response when no cached response is usable.

No subscription/poll interval changes, UI changes, production configuration,
real-key tests, or cross-process coordination are included.

Reference: [Henrik matchlist response codes](https://docs.henrikdev.xyz/valorant/api-reference/matchlist).
