# NOVA Core 3.0 — Load and failure gates

Performance is not accepted by perceived speed alone. Correctness under concurrency and ambiguous network results is a release gate.

## Mandatory invariants

For independent entities under load:
- lost committed operations: 0
- duplicate business transitions: 0
- cross-room/order interference: 0
- global application write lock: prohibited
- stale Sheet overwrite after domain cutover: 0

For repeated identical idempotency keys:
- business transition count: exactly 1
- every replay: returns the already committed result or an equivalent authoritative current result

For same-room competing requests:
- row/state-machine serialization is allowed
- unrelated rooms continue without waiting for that room
- a real semantic conflict returns the current authoritative room and a domain-specific reason, not a generic stale message when avoidable

## Load stages

### Gate A — 200 concurrent users
Run separately and mixed:
- 200 room CLEANING_START requests on independent rooms
- 200 CLEANING_COMPLETE requests on independent rooms
- 200 Houseman order creates
- 200 lost-found creates
- mixed 50/50/50/50 workload
- 200 identical retries using one request ID
- repeated same-room contention scenario

Expected: zero data loss/corruption/duplicates.

### Gate B — 500 concurrent users
Same matrix after Gate A passes. Tune Cloud Run concurrency, DB pool and query indexes from observed evidence only.

### Gate C — 1,000 concurrent users
Capacity proof before broad rollout; not a reason to prematurely over-provision the production database.

## Failure injection matrix

Every migrated mutation must be exercised with:
- client disconnect after request send
- API timeout before response
- API 5xx before DB call
- response lost after DB commit
- retry with same request ID
- Realtime event missed
- app backgrounded during mutation
- app killed after commit but before local acknowledgement
- DB current-state reconcile after restart
- async Sheet mirror failure
- async push failure
- object Storage upload interrupted before finalize

A failure in Sheet, Push, Telegram or reporting after a PostgreSQL commit must never roll back or report the live operation as uncommitted.

## Initial performance objectives

These are objectives, not correctness substitutes:
- normal single mutation P50: 100–200 ms class end-to-end target
- P95: <= 500 ms target under expected production load
- P99: around or below 1 s target where infrastructure permits
- UI: immediate local intent rendering, then authoritative confirmation
- cross-client propagation: sub-second target when Realtime is healthy

Final SLOs are set only after repeatable load-test evidence on the selected Cloud Run and database configuration.