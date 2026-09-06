# NOVA Core 3.0 — Isolated Room State load lab

This load lab exists to prove Cloud Run + PostgreSQL correctness at 200 -> 500 -> 1,000 concurrent requests without touching operational NOVA data.

## Hard isolation rules

The load target is never:
- Apps Script production @271
- Cloud Run `nova-realtime-api`
- Cloud Run `nova-core3-api-dev` while it points to the production Supabase project
- the production Supabase project `evoetxfjmkkjptucwxsv`

The only permitted load target is:
- a separate Supabase development branch with no production rows
- a separate Cloud Run service named `nova-core3-api-load`
- service environment marker `NOVA_CORE_LOAD_DB_MODE=ISOLATED_BRANCH_ONLY`

The load workflow compares the load service `SUPABASE_URL` with production and aborts before traffic if they are equal.

## Supabase branch creation

Creating a Supabase development branch can incur cost. Cost must be retrieved for the owning organization and explicitly confirmed before branch creation.

After creation:
1. verify the branch has zero `nova_users` and zero `nova_rooms_current` rows;
2. verify the Core 3 auth/action/read functions exist on the branch;
3. if required, apply the additive Core 3 migrations to the branch only;
4. apply `db/nova_core3_load_lab_v1.sql` to the branch only;
5. verify the branch contains exactly 8 synthetic `LOAD*` users and 3,409 synthetic rooms for business date `2099-01-01`;
6. verify no non-synthetic user or room exists.

`nova_core3_load_lab_v1.sql` refuses to run when operational users or rooms already exist, which makes accidental execution against production fail before load data is written.

## Cloud Run load service

Deploy the current Core 3 server source to a separate service:

`nova-core3-api-load`

Required environment:
- `SUPABASE_URL` = isolated branch URL
- `SUPABASE_PUBLISHABLE_KEY` = isolated branch publishable key
- `SUPABASE_JWT_SECRET` = signing secret proven compatible with that branch before load execution
- `NOVA_CORE_RPC_TIMEOUT_MS=2500`
- `NOVA_CORE_RPC_ATTEMPTS=3`
- `NOVA_CORE_ACCESS_TOKEN_SECONDS=43200`
- `NOVA_CORE_LOAD_DB_MODE=ISOLATED_BRANCH_ONLY`

Before any load request, prove:
- `/health` returns `nova-core3`;
- the load Supabase URL differs from production;
- synthetic `LOAD200` login succeeds;
- authoritative room read returns only synthetic 2099-01-01 data;
- production `nova-realtime-api` revision is captured for unchanged-after verification.

## Executing gates

The source-controlled trigger is normally dormant:

`core3/testing/load-gate-trigger.json`

To run a gate, temporarily set:
- `enabled: true`
- `stage: "200"`, then `"500"`, then `"1000"`

The push-only workflow `.github/workflows/core3-load-gates.yml` runs the stage and uploads JSON latency/correctness reports. After each execution, return the trigger to `enabled: false`, `stage: "none"` before merge.

Sequence:
1. Gate A 200
2. inspect correctness + latency report
3. Gate B 500 only if A passes
4. inspect report
5. Gate C 1,000 only if B passes
6. return trigger to dormant

No production cutover, PR merge, DB ownership guard activation or Apps Script deployment is part of this load lab.
