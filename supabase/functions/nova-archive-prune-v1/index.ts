import { createClient } from "https://esm.sh/@supabase/supabase-js@2.57.0";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BUCKET = "nova-archive";
const PRUNE_TOKEN_SHA256 = "fae21e69fff5aa5d44a06aab460299df9d15fe393b775a2b1b27ebf1567370b9";
const COMMIT_CONFIRM = "PRUNE_VERIFIED_HOT_DATA";

const db = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

async function sha256Bytes(bytes: Uint8Array) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(digest).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256Text(value: string) {
  return await sha256Bytes(new TextEncoder().encode(value));
}

function safeEqualHex(a: string, b: string) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function authorized(req: Request) {
  const token = String(req.headers.get("x-nova-archive-prune-token") || "").trim();
  if (token.length < 40) return false;
  return safeEqualHex(await sha256Text(token), PRUNE_TOKEN_SHA256);
}

async function gunzip(bytes: Uint8Array) {
  const readable = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(readable).arrayBuffer());
}

function sourceTypeOrNull(value: unknown) {
  const v = String(value || "").trim().toUpperCase();
  if (!v) return null;
  if (v !== "CURRENT_ROOM_HISTORY" && v !== "WORK_HISTORY") throw new Error("INVALID_SOURCE_TYPE");
  return v;
}

async function updateRun(runId: number | null, patch: Record<string, unknown>) {
  if (!runId) return;
  await db.from("nova_archive_prune_runs").update(patch).eq("run_id", runId);
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ ok: false, code: "METHOD_NOT_ALLOWED" }, 405);
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY) return json({ ok: false, code: "SERVER_CONFIG" }, 500);
  if (!(await authorized(req))) return json({ ok: false, code: "UNAUTHORIZED" }, 401);

  let body: any = {};
  try { body = await req.json(); } catch (_) { body = {}; }

  const mode = String(body?.mode || "dry-run").trim().toLowerCase() === "commit" ? "commit" : "dry-run";
  const retentionDays = Math.max(30, Math.min(Number(body?.retentionDays || 30) || 30, 3650));
  let sourceType: string | null = null;
  try { sourceType = sourceTypeOrNull(body?.sourceType); }
  catch { return json({ ok: false, code: "INVALID_SOURCE_TYPE" }, 400); }

  if (mode === "commit" && String(body?.confirm || "") !== COMMIT_CONFIRM) {
    return json({ ok: false, code: "PRUNE_CONFIRM_REQUIRED" }, 400);
  }

  const { data: candidates, error: candidateError } = await db.rpc("nova_archive_retention_candidates_service", {
    p_source_type: sourceType,
    p_older_than_days: retentionDays,
    p_limit: 1,
  });
  if (candidateError) return json({ ok: false, code: "PRUNE_CANDIDATE_LOOKUP_FAILED", message: candidateError.message }, 500);

  const candidate = Array.isArray(candidates) && candidates.length ? candidates[0] : null;
  if (!candidate) {
    return json({ ok: true, processed: false, mode, retentionDays, message: "no eligible prune candidate" });
  }

  const { data: batch, error: batchError } = await db
    .from("nova_archive_batches")
    .select("batch_id,source_type,period_start,period_end,site,object_path,row_count,uncompressed_bytes,compressed_bytes,checksum_sha256,status,verified_at,retired_at,deep_verify_status,last_deep_verified_at")
    .eq("batch_id", candidate.batch_id)
    .maybeSingle();

  if (batchError || !batch) return json({ ok: false, code: "PRUNE_BATCH_LOOKUP_FAILED", message: batchError?.message || "batch missing" }, 500);

  let runId: number | null = null;
  const { data: run } = await db
    .from("nova_archive_prune_runs")
    .insert({
      batch_id: batch.batch_id,
      mode: mode === "commit" ? "COMMIT" : "DRY_RUN",
      status: "STARTED",
      source_type: batch.source_type,
      business_date: batch.period_start,
      site: batch.site,
      expected_rows: Number(batch.row_count || 0),
      checksum_sha256: String(batch.checksum_sha256 || ""),
      message: "prune preflight started",
    })
    .select("run_id")
    .single();
  if (run?.run_id) runId = Number(run.run_id);

  try {
    if (batch.status !== "VERIFIED" || batch.retired_at) throw new Error("PRUNE_BATCH_NOT_ACTIVE_VERIFIED");
    if (batch.deep_verify_status !== "VERIFIED" || !batch.last_deep_verified_at) throw new Error("PRUNE_DEEP_VERIFY_REQUIRED");

    const { data: file, error: downloadError } = await db.storage.from(BUCKET).download(batch.object_path);
    if (downloadError || !file) throw downloadError || new Error("PRUNE_ARCHIVE_OBJECT_MISSING");

    const compressed = new Uint8Array(await file.arrayBuffer());
    if (compressed.byteLength !== Number(batch.compressed_bytes || 0)) throw new Error("PRUNE_COMPRESSED_SIZE_MISMATCH");

    const restored = await gunzip(compressed);
    if (restored.byteLength !== Number(batch.uncompressed_bytes || 0)) throw new Error("PRUNE_UNCOMPRESSED_SIZE_MISMATCH");

    const checksum = await sha256Bytes(restored);
    if (checksum !== String(batch.checksum_sha256 || "")) throw new Error("PRUNE_CHECKSUM_MISMATCH");

    const text = new TextDecoder().decode(restored);
    const lines = text.split("\n").filter((line) => line.length > 0);
    if (lines.length !== Number(batch.row_count || 0)) throw new Error("PRUNE_ARCHIVE_ROW_COUNT_MISMATCH");

    const rows = lines.map((line) => JSON.parse(line));

    if (String(batch.source_type) === "WORK_HISTORY") {
      const { count, error: indexError } = await db
        .from("nova_archive_index")
        .select("archive_key", { count: "exact", head: true })
        .eq("batch_id", batch.batch_id);
      if (indexError) throw indexError;
      if (Number(count || 0) !== Number(batch.row_count || 0)) throw new Error("PRUNE_ARCHIVE_INDEX_MISMATCH");
    }

    const { data: guarded, error: guardError } = await db.rpc("nova_archive_prune_commit_service", {
      p_batch_id: batch.batch_id,
      p_expected_rows: rows,
      p_retention_days: retentionDays,
      p_dry_run: mode !== "commit",
    });
    if (guardError) throw guardError;
    if (!guarded?.ok || !guarded?.eligible) throw new Error("PRUNE_GUARD_REJECTED");

    const deletedRows = Number(guarded?.deletedRows || 0);
    const remainingRows = Number(guarded?.remainingRows ?? (mode === "commit" ? -1 : batch.row_count));

    await updateRun(runId, {
      status: mode === "commit" ? "COMPLETED" : "PASSED",
      deleted_rows: deletedRows,
      remaining_rows: remainingRows,
      message: mode === "commit"
        ? "hot DB pruned after immediate archive verification; archive object retained"
        : "dry-run passed after immediate archive verification; no hot DB rows deleted",
      completed_at: new Date().toISOString(),
    });

    return json({
      ok: true,
      processed: true,
      mode,
      retentionDays,
      batchId: batch.batch_id,
      sourceType: batch.source_type,
      businessDate: batch.period_start,
      site: batch.site,
      rowCount: Number(batch.row_count || 0),
      checksumSha256: checksum,
      priorDeepVerifiedAt: batch.last_deep_verified_at,
      guard: guarded,
      archiveObjectRetained: true,
      storageObjectDeleted: false,
    });
  } catch (error) {
    const message = String((error as any)?.message || error || "prune failed").slice(0, 1200);
    await updateRun(runId, {
      status: "FAILED",
      message,
      completed_at: new Date().toISOString(),
    });
    return json({ ok: false, code: "PRUNE_FAILED", message, batchId: batch.batch_id, mode }, 409);
  }
});
