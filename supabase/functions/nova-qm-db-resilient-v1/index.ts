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

function json(status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...CORS,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
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

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json(405, { ok: false, message: "POST 요청만 지원합니다." });

  const authorization = req.headers.get("Authorization") || "";
  if (!authorization.startsWith("Bearer ")) {
    return json(401, { ok: false, code: "28000", message: "QM 인증정보를 확인할 수 없습니다." });
  }

  // Edge gateway의 verify_jwt=true 검증을 통과한 JWT claims를 기존 DB 함수의
  // request.jwt.claims 컨텍스트로 전달하여 기존 권한/사업장 검증을 그대로 재사용합니다.
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
    return json(400, { ok: false, code: "22023", message: "지원하지 않는 QM DB 복구 작업입니다." });
  }

  const dbUrl = String(Deno.env.get("SUPABASE_DB_URL") || "").trim();
  if (!dbUrl) {
    return json(503, { ok: false, code: "QM_DB_DIRECT_UNAVAILABLE", message: "QM 직접 DB 연결정보가 준비되지 않았습니다." });
  }

  const sql = postgres(dbUrl, {
    prepare: false,
    max: 1,
    idle_timeout: 5,
    connect_timeout: 5,
  });

  try {
    const result = await sql.begin(async (tx) => {
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
        const rows = await tx`
          select to_jsonb(public.nova_save_qm_draft(
            ${String(args.p_draft_id || "")},
            ${String(args.p_business_date || "")}::date,
            ${String(args.p_site || "")},
            ${String(args.p_room_no || "")},
            ${String(args.p_checklist_revision || "")},
            ${JSON.stringify(args.p_answers ?? [])}::jsonb,
            ${JSON.stringify(args.p_defects ?? [])}::jsonb,
            ${Number(args.p_expected_version || 0)}::bigint,
            ${String(args.p_request_id || "")}
          )) as result
        `;
        return rows[0]?.result ?? null;
      }

      const rows = await tx`
        select public.nova_qm_inspection_finalize_v2(
          ${JSON.stringify(args.p_payload ?? {})}::jsonb,
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
        "X-NOVA-QM-Transport": "direct-db-edge-v1",
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
  } finally {
    try { await sql.end({ timeout: 1 }); } catch (_) {}
  }
});
