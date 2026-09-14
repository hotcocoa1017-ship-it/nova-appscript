# NOVA Core 3.0

NOVA Core 3.0 is the server-based successor to the Apps Script-centered NOVA room-management system.

## Frozen production baseline

- Apps Script production deployment: `@271`
- Production source commit: `8bc4540a7ac1aa758186521f206e147685070329`
- Immutable rollback branch: `backup/nova-room-prod-271-20260906`
- Baseline record: GitHub issue #20

The backup branch is never a development target. Existing @271 remains the live operational system until a Core 3.0 cutover gate explicitly passes.

## Target architecture

```text
Flutter employee app (Android + iOS)       Admin/ORDER Web
                  \                         /
                   \                       /
                      NOVA Core API
                         Cloud Run
                            |
                    PostgreSQL/Supabase
                    /        |        \
             Realtime     Storage    Event/Outbox
                 |                       |
            live clients             Async Worker
                                        |
                              Sheets / Push / Telegram
                              Reports / Statistics
```

## Non-negotiable rules

1. PostgreSQL commit is the success point for live operations.
2. Google Sheets never decides live room/QM/houseman state after cutover. It is one-way reporting/mirror/backup only.
3. Realtime is a fast notification channel, not the source of truth. Every reconnect/foreground resume reconciles against PostgreSQL.
4. Every mutation uses an idempotency/request ID enforced by the database.
5. Unrelated rooms/orders never share a global application lock.
6. True same-entity conflicts are serialized by row/state-machine rules; already-achieved identical intent converges to success where safe.
7. Client role/employee/site values are never trusted for authorization. The server/DB validates authenticated identity and current assignment.
8. Images upload directly to object storage by signed authorization; API stores metadata and lifecycle state.
9. Android and iOS are equal first-class release targets. A feature complete on only one OS is not complete.
10. No production cutover without dedicated tests, @271 regression parity, syntax/static validation, idempotency tests, concurrency tests, failure recovery tests and post-deploy verification.

## Initial migration order

Phase 1 is Room State: roommaid cleaning START/COMPLETE, assignment and indicator/current-state reads. Then QM, Houseman, photos/push, Public, close/reporting and remaining domains follow.

The transitional branch may contain compatibility code, but the final Core 3.0 architecture must remove migrated legacy Sheet write fallbacks rather than accumulate permanent fallback paths.