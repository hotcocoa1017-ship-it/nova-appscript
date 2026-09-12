import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import postgres from "npm:postgres@3.4.5";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const ALLOWED = new Set([
  "nova_qm_begin_inspection_v1",
  "nova_qm_prepare_new_draft_v1",
  "nova_save_qm_draft",
  "nova_qm_inspection_finalize_v2",
]);

const DB_URL = String(Deno.env.get("SUPABASE_DB_URL") || "").trim();
// QM_FAST_PATH_EDGE_V2 · warm Edge instance에서 DB pool을 재사용해 매 요청 connect/end 비용을 제거합니다.
const SQL = DB_URL ? postgres(DB_URL, {
  prepare: false,
  max: 2,
  idle_timeout: 20,
  connect_timeout: 5,
}) : null;

function json(status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...CORS,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-NOVA-QM-Transport": "direct-db-edge-v2",
    },
  });
}

function decodeJwtPayload(authorization: string): Record<string, unknown> | null {
  const token = authorization.replace(/^Bearer\s+/i, "").trim();
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}

function errorStatus(code: string) {
  const normalized = String(code || "").trim().toUpperCase();
  if (["42501", "28000"].includes(normalized)) return 403;
  if (normalized === "P0002") return 404;
  if (["40001", "55000", "23505"].includes(normalized)) return 409;
  if (["22023", "22P02", "22007"].includes(normalized)) return 400;
  return 500;
}

function appError(message: string, code = "22023") {
  const error = new Error(message) as Error & { code?: string };
  error.code = code;
  return error;
}

function parseJsonValue(value: unknown): unknown {
  let current = value;
  // 과거 이중 JSON 문자열도 2단계까지만 안전하게 복원합니다.
  for (let i = 0; i < 2 && typeof current === "string"; i += 1) {
    const text = current.trim();
    if (!text) return null;
    try { current = JSON.parse(text); }
    catch { return current; }
  }
  return current;
}

function jsonArray(value: unknown, label: string): unknown[] {
  const parsed = parseJsonValue(value ?? []);
  if (!Array.isArray(parsed)) throw appError(`${label} 데이터 형식이 올바르지 않습니다.`);
  return parsed;
}

function jsonObject(value: unknown, label: string): Record<string, unknown> {
  const parsed = parseJsonValue(value ?? {});
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw appError(`${label} 데이터 형식이 올바르지 않습니다.`);
  }
  return parsed as Record<string, unknown>;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json(405, { ok: false, message: "POST 요청만 지원합니다." });

  const authorization = req.headers.get("Authorization") || "";
  if (!authorization.startsWith("Bearer ")) {
    return json(401, { ok: false, code: "28000", message: "QM 인증정보를 확인할 수 없습니다." });
  }

  const claims = decodeJwtPayload(authorization);
  const employeeNo = String(claims?.employee_no || "").trim();
  if (!claims || !employeeNo) {
    return json(403, { ok: false, code: "42501", message: "QM 사용자 인증정보를 확인할 수 없습니다." });
  }

  let body: any = {};
  try {
    body = await req.json();
  } catch {
    return json(400, { ok: false, code: "22023", message: "요청 형식이 올바르지 않습니다." });
  }

  const rpc = String(body?.rpc || "").trim();
  const args = body?.args && typeof body.args === "object" ? body.args : {};
  if (!ALLOWED.has(rpc)) {
    return json(400, { ok: false, code: "22023", message: "지원하지 않는 QM DB 작업입니다." });
  }

  if (!SQL) {
    return json(503, { ok: false, code: "QM_DB_DIRECT_UNAVAILABLE", message: "QM 직접 DB 연결정보가 준비되지 않았습니다." });
  }

  try {
    const result = await SQL.begin(async (tx) => {
      await tx`select set_config('request.jwt.claims', ${JSON.stringify(claims)}, true)`;

      if (rpc === "nova_qm_begin_inspection_v1") {
        const rows = await tx`
          select public.nova_qm_begin_inspection_v1(
            ${String(args.p_business_date || "")}::date,
            ${String(args.p_site || "")},
            ${String(args.p_room_no || "")},
            ${String(args.p_view || "TARGETS")},
            ${String(args.p_request_id || "")}
          ) as result
        `;
        return rows[0]?.result ?? null;
      }

      if (rpc === "nova_qm_prepare_new_draft_v1") {
        const rows = await tx`
          select public.nova_qm_prepare_new_draft_v1(
            ${String(args.p_business_date || "")}::date,
            ${String(args.p_site || "")},
            ${String(args.p_room_no || "")},
            ${Number(args.p_expected_room_version || 0)}::bigint,
            ${String(args.p_request_id || "")}
          ) as result
        `;
        return rows[0]?.result ?? null;
      }

      if (rpc === "nova_save_qm_draft") {
        const answers = jsonArray(args.p_answers, "QM answers");
        const defects = jsonArray(args.p_defects, "QM defects");
        const rows = await tx`
          select to_jsonb(public.nova_save_qm_draft(
            ${String(args.p_draft_id || "")},
            ${String(args.p_business_date || "")}::date,
            ${String(args.p_site || "")},
            ${String(args.p_room_no || "")},
            ${String(args.p_checklist_revision || "")},
            ${JSON.stringify(answers)}::jsonb,
            ${JSON.stringify(defects)}::jsonb,
            ${Number(args.p_expected_version || 0)}::bigint,
            ${String(args.p_request_id || "")}
          )) as result
        `;
        return rows[0]?.result ?? null;
      }

      const payload = jsonObject(args.p_payload, "QM finalize payload");
      const rows = await tx`
        select public.nova_qm_inspection_finalize_v2(
          ${JSON.stringify(payload)}::jsonb,
          ${String(args.p_request_id || "")}
        ) as result
      `;
      return rows[0]?.result ?? null;
    });

    if (result === null || typeof result === "undefined") {
      return json(500, { ok: false, code: "QM_DB_DIRECT_EMPTY", message: "QM 직접 DB 응답을 확인할 수 없습니다." });
    }

    return new Response(JSON.stringify(result), {
      status: 200,
      headers: {
        ...CORS,
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-NOVA-QM-Transport": "direct-db-edge-v2",
      },
    });
  } catch (error: any) {
    console.error("nova-qm-db-resilient-v1", rpc, error);
    const code = String(error?.code || "QM_DB_DIRECT_ERROR").trim();
    return json(errorStatus(code), {
      ok: false,
      code,
      message: String(error?.message || "QM 직접 DB 처리 중 오류가 발생했습니다."),
      details: String(error?.detail || error?.details || ""),
      hint: String(error?.hint || ""),
    });
  }
});
