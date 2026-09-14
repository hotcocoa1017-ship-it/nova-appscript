# NOVA Core 3 — Cloud Run Dev Deployment

The first Core 3 server is deployed only to an isolated development service.
It must never replace or modify the existing `nova-realtime-api` service during
Phase 1 validation.

- GCP project: `project-6a8144e9-31f3-4d5c-b9b`
- Region: `asia-southeast1`
- Existing production Realtime service: `nova-realtime-api` (read-only preflight source)
- Core 3 development target: `nova-core3-api-dev`
- Container source: `core3/server`
- Health endpoint: `GET /health`
- Employee room read: `GET /v1/rooms?businessDate=...&site=...`
- Room mutation: `POST /v1/rooms/{roomNo}/actions`

## Hard isolation rules

1. The existing production Realtime service is never updated by the Core 3 dev workflow.
2. Apps Script deployment @271 is not touched by Core 3 workflows.
3. Employee calls forward the employee JWT and use a publishable Supabase API key;
   no service-role credential is exposed to the client or used to bypass employee authorization.
4. Dev deployment is allowed only after Core CI, WIF preflight, environment-source
   checks and local container build pass.
5. Production cutover requires separate approval and the full load/failure/parity gates.
