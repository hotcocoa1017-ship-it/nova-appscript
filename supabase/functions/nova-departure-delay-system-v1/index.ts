import { createClient } from "https://esm.sh/@supabase/supabase-js@2.57.0";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
// Server-only compatibility key already used by NOVA Apps Script -> Supabase server calls.
// Browser code never receives this key. This function exposes only departure-delay claim/finalize.
const NOVA_SYSTEM_KEY_SHA256 = "c897feff05ce3a3ffbc586f788e78ee7ea95281e44209b3aa94767d96ee46de3";

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
  const key = String(req.headers.get("x-nova-system-key") || "").trim();
  if (key.length < 40) return false;
  return safeEqualHex(await sha256Text(key), NOVA_SYSTEM_KEY_SHA256);
}

function text(value: unknown, max: number) {
  return String(value ?? "").trim().slice(0, max);
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ ok: false, code: "METHOD_NOT_ALLOWED" }, 405);
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY) return json({ ok: false, code: "SERVER_CONFIG" }, 500);
  if (!(await authorized(req))) return json({ ok: false, code: "UNAUTHORIZED" }, 401);

  let body: any = {};
  try { body = await req.json(); } catch (_) { body = {}; }
  const action = text(body?.action, 30).toLowerCase();
  const payload = body?.payload && typeof body.payload === "object" ? body.payload : {};

  if (action === "claim") {
    const businessDate = text(payload?.businessDate, 10);
    const claimToken = text(payload?.claimToken, 180);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(businessDate) || !/^[A-Za-z0-9._:-]{8,180}$/.test(claimToken)) {
      return json({ ok: false, code: "INVALID_CLAIM_INPUT" }, 400);
    }
    const { data, error } = await db.rpc("nova_departure_delay_claim_service_v1", {
      p_business_date: businessDate,
      p_claim_token: claimToken,
    });
    if (error) return json({ ok: false, code: "CLAIM_FAILED", message: error.message }, 500);
    return json(data || { ok: false, code: "EMPTY_CLAIM_RESPONSE" }, data?.ok ? 200 : 500);
  }

  if (action === "finalize") {
    const claimToken = text(payload?.claimToken, 180);
    const results = Array.isArray(payload?.results) ? payload.results.slice(0, 5000) : [];
    if (!/^[A-Za-z0-9._:-]{8,180}$/.test(claimToken)) {
      return json({ ok: false, code: "INVALID_FINALIZE_INPUT" }, 400);
    }
    const { data, error } = await db.rpc("nova_departure_delay_finalize_service_v1", {
      p_claim_token: claimToken,
      p_results: results,
    });
    if (error) return json({ ok: false, code: "FINALIZE_FAILED", message: error.message }, 500);
    return json(data || { ok: false, code: "EMPTY_FINALIZE_RESPONSE" }, data?.ok ? 200 : 500);
  }

  return json({ ok: false, code: "ACTION_REQUIRED" }, 400);
});
