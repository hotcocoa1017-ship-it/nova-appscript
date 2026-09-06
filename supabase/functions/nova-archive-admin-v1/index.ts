import { createClient } from "https://esm.sh/@supabase/supabase-js@2.57.0";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BUCKET = "nova-archive";
const ARCHIVE_ADMIN_KEY_SHA256 = "c897feff05ce3a3ffbc586f788e78ee7ea95281e44209b3aa94767d96ee46de3";

const db = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

async function sha256Text(value: string) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
  return Array.from(digest).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function safeEqualHex(a: string, b: string) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function authorized(req: Request) {
  const key = String(req.headers.get("x-nova-archive-admin-key") || "").trim();
  if (key.length < 40) return false;
  return safeEqualHex(await sha256Text(key), ARCHIVE_ADMIN_KEY_SHA256);
}

function text(value: unknown, max: number) {
  return String(value ?? "").trim().slice(0, max);
}

function normalizeFilters(body: any) {
  const businessDate = text(body?.businessDate, 10);
  if (businessDate && !/^\d{4}-\d{2}-\d{2}$/.test(businessDate)) {
    throw new Error("INVALID_BUSINESS_DATE");
  }
  return {
    sourceType: text(body?.sourceType || "WORK_HISTORY", 40),
    businessDate,
    site: text(body?.site, 80),
    roomNo: text(body?.roomNo, 40),
    employeeNo: text(body?.employeeNo, 50),
    recordType: text(body?.recordType, 80),
    archiveKey: text(body?.archiveKey, 160),
    limit: Math.max(1, Math.min(Number(body?.limit || 100) || 100, 200)),
  };
}

async function gunzip(bytes: Uint8Array) {
  const readable = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(readable).arrayBuffer());
}

function lineNumberFromKey(value: unknown) {
  const match = /^line:(\d+)$/.exec(String(value || ""));
  return match ? Number(match[1]) : 0;
}

async function handleStatus() {
  const { data: current, error: currentError } = await db.rpc("nova_archive_integrity_service");
  if (currentError) return json({ ok: false, code: "INTEGRITY_LOOKUP_FAILED" }, 500);

  const { data: latestSnapshot, error: snapshotError } = await db
    .from("nova_archive_integrity_snapshots")
    .select("snapshot_id,checked_at,ok,metrics")
    .order("checked_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (snapshotError) return json({ ok: false, code: "SNAPSHOT_LOOKUP_FAILED" }, 500);

  const { data: prune, error: pruneError } = await db.rpc("nova_archive_prune_status_service");
  if (pruneError) return json({ ok: false, code: "PRUNE_STATUS_LOOKUP_FAILED" }, 500);

  return json({
    ok: true,
    healthy: Boolean(current?.ok),
    current,
    prune: prune || null,
    latestSnapshot: latestSnapshot || null,
  });
}

async function handleQuery(body: any) {
  let filters;
  try {
    filters = normalizeFilters(body);
  } catch {
    return json({ ok: false, code: "INVALID_BUSINESS_DATE" }, 400);
  }

  let query = db
    .from("nova_archive_index")
    .select("archive_key,source_type,business_date,site,room_no,record_type,employee_no,status,source_record_id,object_path,object_record_key,schema_version,archived_at,batch_id");

  if (filters.archiveKey) query = query.eq("archive_key", filters.archiveKey);
  if (filters.sourceType) query = query.eq("source_type", filters.sourceType);
  if (filters.businessDate) query = query.eq("business_date", filters.businessDate);
  if (filters.site) query = query.eq("site", filters.site);
  if (filters.roomNo) query = query.eq("room_no", filters.roomNo);
  if (filters.employeeNo) query = query.eq("employee_no", filters.employeeNo);
  if (filters.recordType) query = query.eq("record_type", filters.recordType);

  const { data, error } = await query
    .order("business_date", { ascending: false })
    .order("archived_at", { ascending: false })
    .limit(filters.limit);

  if (error) return json({ ok: false, code: "ARCHIVE_QUERY_FAILED" }, 500);
  const rows = Array.isArray(data) ? data : [];
  return json({ ok: true, count: rows.length, limit: filters.limit, filters, rows });
}

async function handleRestore(body: any) {
  const archiveKey = text(body?.archiveKey, 160);
  if (!archiveKey) return json({ ok: false, code: "ARCHIVE_KEY_REQUIRED" }, 400);

  const { data: pointer, error: pointerError } = await db
    .from("nova_archive_index")
    .select("archive_key,source_type,business_date,site,room_no,record_type,employee_no,status,source_record_id,source_row_number,object_path,object_record_key,schema_version,archived_at,batch_id")
    .eq("archive_key", archiveKey)
    .maybeSingle();

  if (pointerError) return json({ ok: false, code: "POINTER_LOOKUP_FAILED" }, 500);
  if (!pointer) return json({ ok: false, code: "ARCHIVE_NOT_FOUND" }, 404);

  const lineNumber = lineNumberFromKey(pointer.object_record_key);
  if (!lineNumber) return json({ ok: false, code: "INVALID_OBJECT_RECORD_KEY" }, 500);

  const { data: file, error: downloadError } = await db.storage.from(BUCKET).download(pointer.object_path);
  if (downloadError || !file) return json({ ok: false, code: "ARCHIVE_DOWNLOAD_FAILED" }, 500);

  try {
    const compressed = new Uint8Array(await file.arrayBuffer());
    const restored = await gunzip(compressed);
    const rawLine = new TextDecoder().decode(restored).split("\n")[lineNumber - 1];
    if (!rawLine) return json({ ok: false, code: "ARCHIVE_RECORD_MISSING" }, 409);

    const record = JSON.parse(rawLine);
    const restoredId = String(record?.request_id || record?.id || "");
    if (restoredId !== String(pointer.source_record_id || "")) {
      return json({ ok: false, code: "ARCHIVE_IDENTITY_MISMATCH" }, 409);
    }

    return json({
      ok: true,
      archiveKey,
      restored: true,
      pointer: {
        sourceType: pointer.source_type,
        businessDate: pointer.business_date,
        site: pointer.site,
        roomNo: pointer.room_no,
        recordType: pointer.record_type,
        employeeNo: pointer.employee_no,
        status: pointer.status,
        sourceRecordId: pointer.source_record_id,
        sourceRowNumber: pointer.source_row_number,
        objectPath: pointer.object_path,
        objectRecordKey: pointer.object_record_key,
        schemaVersion: pointer.schema_version,
        batchId: pointer.batch_id,
        archivedAt: pointer.archived_at,
      },
      record,
    });
  } catch {
    return json({ ok: false, code: "RESTORE_FAILED" }, 500);
  }
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ ok: false, code: "METHOD_NOT_ALLOWED" }, 405);
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY) return json({ ok: false, code: "SERVER_CONFIG" }, 500);
  if (!(await authorized(req))) return json({ ok: false, code: "UNAUTHORIZED" }, 401);

  let body: any = {};
  try { body = await req.json(); } catch (_) { body = {}; }
  const action = text(body?.action, 30).toLowerCase();
  const payload = body?.payload && typeof body.payload === "object" ? body.payload : {};

  if (action === "status") return await handleStatus();
  if (action === "query") return await handleQuery(payload);
  if (action === "restore") return await handleRestore(payload);
  return json({ ok: false, code: "ACTION_REQUIRED" }, 400);
});
