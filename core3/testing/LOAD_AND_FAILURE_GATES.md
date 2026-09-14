# NOVA Core 3.0 — Load and failure gates

Performance is not accepted by perceived speed alone. Correctness under concurrency and ambiguous network results is a release gate.

## Current Phase 1 status

Room State is the only domain eligible for live Core 3 load testing in this phase.

Completed before load execution:
- Core server syntax/tests/container build: PASS
- isolated Cloud Run `nova-core3-api-dev`: deployed and health/session guarded
- Flutter Android analyze/test/build and iOS no-sign build: PASS
- private Supabase Realtime authenticated channel subscribe smoke: PASS
- authoritative DB reconcile path without trusting Realtime payload: implemented
- production Apps Script @271: unchanged

Prepared but deliberately not executed against production data:
- `core3/testing/room-state-load.mjs`
- `db/nova_core3_load_lab_v1.sql`
- `.github/workflows/core3-load-gates.yml`

The load seed refuses to run if operational NOVA users or rooms exist. The load workflow also refuses to run when its Supabase URL equals production or when the isolated-load marker is absent.

Houseman, lost-found, photos and other domain load gates remain mandatory when those domains migrate to Core 3. They are not counted as Room State Phase 1 acceptance.

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
- same-intent competitors converge to the achieved authoritative state rather than producing spurious stale-state failures
- a real semantic conflict returns the current authoritative room and a domain-specific reason

## Room State isolated load stages

All stages run only against a separate Supabase development branch plus separate Cloud Run service `nova-core3-api-load`. Production `nova-realtime-api`, Apps Script @271 and production room rows are never load-test targets.

### Gate A — 200 concurrent requests
Run:
- 200 independent `CLEANING_START`
- 200 independent `CLEANING_COMPLETE`
- 200 identical retries with one request ID on one room
- 200 distinct same-intent requests contending on one room
- response discarded after DB commit, then retry with the same request ID
- client timeout/abort, then retry with the same request ID
- Realtime absent, then authoritative DB current-state reconcile

Expected: zero data loss/corruption/duplicates, exact final state/version, production service revision unchanged.

### Gate B — 500 concurrent requests
After Gate A passes:
- 500 independent `CLEANING_START`
- 500 independent `CLEANING_COMPLETE`
- 500 identical retries on one room
- 500 same-room same-intent contenders

Tune Cloud Run concurrency, database behavior or indexes only from observed evidence.

### Gate C — 1,000 concurrent requests
After Gate B passes, repeat the same Room State matrix at 1,000 concurrent requests. This is the capacity proof before broad rollout, not a reason to prematurely over-provision production.

## Failure injection matrix

Every migrated mutation must eventually be exercised with:
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

For Room State Phase 1, the isolated harness covers ambiguous retry, post-commit response discard, timeout/abort and no-Realtime authoritative reconcile. Mobile controller tests cover stale refresh protection during an in-flight optimistic mutation. Remaining failure modes are added before the specific downstream subsystem becomes a production cutover dependency.

A failure in Sheet, Push, Telegram or reporting after a PostgreSQL commit must never roll back or report the live operation as uncommitted.

## Initial performance objectives

These are objectives, not correctness substitutes:
- normal single mutation P50: 100–200 ms class end-to-end target
- P95: <= 500 ms target under expected production load
- P99: around or below 1 s target where infrastructure permits
- UI: immediate local intent rendering, then authoritative confirmation
- cross-client propagation: sub-second target when Realtime is healthy

Every load report records P50/P95/P99/max latency, but correctness failures are hard failures regardless of latency. Final SLOs are set only after repeatable isolated Cloud Run + database evidence.
