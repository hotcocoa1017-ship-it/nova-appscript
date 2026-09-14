# NOVA Core 3.0 — Phase 1 Room State Contract

## Purpose

NOVA Core 3.0 migrates the live room-operation path away from Google Sheets and Apps Script as an operational database.

Phase 1 scope is intentionally narrow:

- room assignment
- cleaning start
- cleaning complete
- cleaning reset / clear assignment
- QM assignment and room cleaning-state transitions
- operational room status
- indicator/mobile current-state reads
- Realtime change notification
- DB -> Sheet asynchronous mirror

Current production remains the operational system until every cutover gate below passes.

## Single source of truth

For Phase 1 operational fields, `public.nova_rooms_current` is the only authoritative current state.

DB-owned fields:

- `room_status`
- `cleaning_status`
- `cleaning_type`
- `assignment_type`
- `roommaid_employee_no`
- `secondary_roommaid_employee_no`
- `qm_employee_no`
- `operational_status`
- `version`
- `cleaning_started_at`
- `cleaning_completed_at`
- `updated_by`
- `updated_at`

Google Sheets may contain a mirror of these values for reports, closing, printing and legacy compatibility, but a stale Sheet value must never be allowed to overwrite a newer DB value after Phase 1 cutover.

## Existing database primitives to preserve

Production already has useful Core primitives and they must be reused rather than replaced without cause:

1. `nova_rooms_current`
   - unique `(business_date, site, room_no)`
   - monotonic room `version`
2. `nova_room_events`
   - unique `request_id`
   - before/after state, actor, room version, event time
3. `nova_request_dedup`
   - primary key `request_id`
   - response replay support for idempotent writes
4. RLS enabled on all three core tables.
5. Realtime Broadcast is used as a fast notification path.
6. DB -> Sheet event mirror is retained as asynchronous compatibility/reporting infrastructure.

## Mandatory invariants

### Write invariants

Every operational write must satisfy all of the following:

- authenticated user
- site authorization checked by the server/database
- role authorization checked by the server/database
- assignment/ownership rules checked by the server/database where applicable
- one stable `requestId` per user action
- repeated identical `requestId` returns the original result and does not create a second state transition
- room row is locked or version-checked in the same transaction as the transition
- room `version` increases exactly when current state changes
- a successful state transition creates exactly one corresponding event
- API success is defined by committed PostgreSQL state, not by Sheet, Telegram or Realtime delivery

### Read invariants

- initial screen may use cached UI state for instant render
- authoritative refresh always reads PostgreSQL current state
- Realtime is notification only; it is never the final source of truth
- reconnect/foreground resume must reconcile with PostgreSQL
- missed Realtime delivery must self-heal through current-state reconciliation

### Mirror invariants

- DB -> Sheet is one-way for Phase 1 DB-owned fields
- Sheet mirror failure never changes API success to failure
- mirror is retryable and idempotent by `requestId`
- mirror backlog must be observable
- a Sheet row may lag DB, but DB may never be rolled back because a Sheet row is older

## Current transitional risk that must be removed

`RealtimeDailySync.js` still contains transitional Sheets -> PostgreSQL paths:

- scheduled current-room forward sync
- JIT single-room sync before some actions
- a 5-minute forward-sync cadence inside `novaRealtimeScheduledFinalSync`

These were appropriate during migration, but become unsafe once the DB is declared authoritative for Phase 1 fields.

The Phase 1 cutover must therefore separate:

1. **bootstrap/import fields** that may still originate from Sheets at business-day load time, from
2. **live operational fields** that are DB-owned after bootstrap.

A scheduled Sheet sync must never overwrite live operational fields after that room has entered DB ownership.

## Phase 1 implementation sequence

### P1-A — Contract and audit (no production write)

- freeze current production baseline
- audit schema, indexes, constraints, RLS, execute privileges
- audit event/state consistency for the current business date
- document current transition graph
- add automated read-only Core audit queries

### P1-B — DB-authoritative boundary

Introduce an explicit server-side ownership rule for room state.

Target behavior:

- business-day bootstrap may create missing room rows from Sheets
- bootstrap may update non-operational descriptive fields only
- normal scheduled sync cannot overwrite DB-owned live fields
- explicit disaster-recovery import must require a separate ADMIN-only operation and audit record

Do not rely only on a browser flag for this boundary; the write protection must exist in the server/database path.

### P1-C — Unified Room State API

All room mutations converge on one state-engine contract, even if compatibility endpoints remain temporarily:

- assignment
- START
- COMPLETE
- RESET
- QM_ASSIGN
- QM_START
- QM_COMPLETE
- QM_REWORK
- operational status
- room status where applicable

Each mutation returns:

- `ok`
- `requestId`
- `room`
- `version`
- `eventId` when a state change occurred
- `idempotent`
- server timing

### P1-D — Read path

- indicator reads DB current state
- ROOMMAID reads only own assigned DB rows
- QM reads only relevant DB rows
- Realtime push remains fast path
- current-state reconciliation remains mandatory fallback

### P1-E — Sheet dependency removal

For Phase 1 operations, no interactive request may wait for:

- Spreadsheet write lock
- history row append
- Sheet flush
- Telegram send
- report generation

Those become background consumers of committed DB events.

### P1-F — Cutover

Cutover only when all gates pass.

## Cutover gates

A release is blocked unless all are true:

1. existing NOVA release regression gate passes
2. existing QM end-to-end gate passes
3. Core room-state audit returns zero critical inconsistencies
4. duplicate `(business_date,site,room_no)` = 0
5. duplicate event `request_id` = 0
6. current room version behind latest event version = 0
7. invalid roommaid/QM assignments = 0
8. START/COMPLETE invalid state transitions = 0
9. simulated duplicate request produces one transition only
10. timeout/response-loss simulation converges to committed DB state
11. missed Broadcast simulation converges through DB reconciliation
12. Sheet mirror disabled/failing simulation does not affect operational success
13. rollback procedure tested before production cutover

## Rollback policy

Rollback is application-routing rollback, not data rollback.

Never restore stale Sheet values over committed DB state merely to roll back code.

If a new Core client/API revision is unhealthy:

- stop routing new traffic to the unhealthy revision
- keep PostgreSQL current state and events intact
- deploy/re-enable the previous known-good API/client revision
- replay any asynchronous mirror backlog from DB events

## Phase 1 non-goals

Do not rewrite these yet:

- HR/leave
- monthly reports
- payroll exports
- archive UI
- all historical Sheets
- employee-facing Flutter application

The employee app is built only after the Core API contract is stable.

## Definition of Phase 1 complete

Phase 1 is complete when Apps Script/Google Sheets can be unavailable for several minutes and all of the following still work correctly:

- room assignment
- roommaid START/COMPLETE
- QM state flow covered by Room State
- operational status
- indicator current state
- mobile current state
- Realtime notification and reconnect reconciliation

Sheets may be temporarily stale, but when service resumes they catch up from DB events without affecting live room operations.
