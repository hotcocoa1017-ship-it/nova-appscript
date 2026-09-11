import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const BUCKET = "nova-houseman-photos";
const MAX_PHOTOS = 5;
const MAX_BYTES = 2_621_440;
const THUMB_WIDTH = 256;
const THUMB_HEIGHT = 256;
const THUMB_QUALITY = 55;
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

function safeSegment(value: unknown, fallback: string) {
  const text = String(value ?? "").trim().replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "");
  return (text || fallback).slice(0, 80);
}

function validClientId(value: unknown) {
  return /^[A-Za-z0-9._:-]{1,120}$/.test(String(value ?? ""));
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json(405, { ok: false, message: "POST 요청만 지원합니다." });

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const authorization = req.headers.get("Authorization") ?? "";
  if (!supabaseUrl || !anonKey || !serviceRoleKey || !authorization.startsWith("Bearer ")) {
    return json(401, { ok: false, message: "사진 인증정보를 확인할 수 없습니다." });
  }

  let body: any = {};
  try { body = await req.json(); } catch { return json(400, { ok: false, message: "요청 형식이 올바르지 않습니다." }); }
  const action = String(body.action ?? "").trim().toLowerCase();
  const orderId = String(body.orderId ?? "").trim();
  if (!orderId) return json(400, { ok: false, message: "하우스맨 요청번호가 없습니다." });

  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const admin = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const mode = action === "view" || action === "thumbnail" ? "VIEW" : "UPLOAD";
  const { data: authz, error: authError } = await userClient.rpc("nova_houseman_photo_authorize", {
    p_order_id: orderId,
    p_mode: mode,
  });
  if (authError || !authz?.ok) return json(403, { ok: false, message: authError?.message || "사진 권한을 확인할 수 없습니다." });

  try {
    if (action === "prepare") {
      const incoming = Array.isArray(body.photos) ? body.photos : [];
      if (!incoming.length || incoming.length > MAX_PHOTOS) return json(400, { ok: false, message: "사진은 1~5장까지 준비할 수 있습니다." });
      for (const photo of incoming) {
        if (!validClientId(photo?.clientPhotoId)) return json(400, { ok: false, message: "사진 식별값이 올바르지 않습니다." });
        if (String(photo?.mimeType || "").toLowerCase() !== "image/jpeg") return json(400, { ok: false, message: "JPG 사진만 등록할 수 있습니다." });
        const size = Number(photo?.sizeBytes || 0);
        if (!Number.isFinite(size) || size < 1 || size > MAX_BYTES) return json(400, { ok: false, message: "사진은 2.5MB 이하로 등록하세요." });
      }

      const cutoff = new Date(Date.now() - 30 * 60 * 1000).toISOString();
      const { data: stale } = await admin.from("nova_houseman_order_photos")
        .select("photo_id,object_path")
        .eq("order_id", orderId).eq("status", "PENDING").lt("created_at", cutoff);
      if (stale?.length) {
        const paths = stale.map((row: any) => row.object_path).filter(Boolean);
        if (paths.length) await admin.storage.from(BUCKET).remove(paths).catch(() => null);
        await admin.from("nova_houseman_order_photos").delete().in("photo_id", stale.map((row: any) => row.photo_id));
      }

      const { data: existing, error: existingError } = await admin.from("nova_houseman_order_photos")
        .select("photo_id,order_id,client_photo_id,bucket_id,object_path,file_name,mime_type,size_bytes,uploaded_by,status,created_at,uploaded_at")
        .eq("order_id", orderId);
      if (existingError) throw existingError;
      const byClient = new Map((existing || []).map((row: any) => [String(row.client_photo_id), row]));
      const newCount = incoming.filter((p: any) => !byClient.has(String(p.clientPhotoId))).length;
      if ((existing?.length || 0) + newCount > MAX_PHOTOS) return json(409, { ok: false, message: `요청사진은 최대 ${MAX_PHOTOS}장까지 등록할 수 있습니다.` });

      const prepared: any[] = [];
      for (let i = 0; i < incoming.length; i++) {
        const src = incoming[i];
        const clientPhotoId = String(src.clientPhotoId);
        let row: any = byClient.get(clientPhotoId);
        if (!row) {
          const photoId = crypto.randomUUID();
          const objectPath = [
            safeSegment(authz.businessDate, "date"),
            safeSegment(authz.site, "site"),
            safeSegment(authz.roomNo, "room"),
            safeSegment(orderId, "order"),
            `${photoId}.jpg`,
          ].join("/");
          const fileName = safeSegment(String(src.fileName || `photo_${i + 1}.jpg`).replace(/\.jpg$/i, ""), `photo_${i + 1}`) + ".jpg";
          const { data: inserted, error: insertError } = await admin.from("nova_houseman_order_photos").insert({
            photo_id: photoId,
            order_id: orderId,
            client_photo_id: clientPhotoId,
            bucket_id: BUCKET,
            object_path: objectPath,
            file_name: fileName,
            mime_type: "image/jpeg",
            size_bytes: Number(src.sizeBytes || 0),
            uploaded_by: String(authz.employeeNo || ""),
            status: "PENDING",
          }).select().single();
          if (insertError) {
            const { data: raced } = await admin.from("nova_houseman_order_photos").select("*").eq("order_id", orderId).eq("client_photo_id", clientPhotoId).maybeSingle();
            if (!raced) throw insertError;
            row = raced;
          } else row = inserted;
        }

        if (String(row.status) === "READY") {
          prepared.push({ clientPhotoId, photoId: row.photo_id, ready: true, duplicate: true });
          continue;
        }
        if (String(row.uploaded_by) !== String(authz.employeeNo || "")) return json(403, { ok: false, message: "사진 준비 소유권을 확인할 수 없습니다." });
        const { data: signed, error: signedError } = await admin.storage.from(BUCKET).createSignedUploadUrl(String(row.object_path));
        if (signedError || !signed?.token) throw signedError || new Error("사진 업로드 URL을 만들지 못했습니다.");
        prepared.push({
          clientPhotoId,
          photoId: row.photo_id,
          path: row.object_path,
          token: signed.token,
          signedUrl: signed.signedUrl || "",
          ready: false,
          duplicate: false,
        });
      }

      return json(200, { ok: true, bucket: BUCKET, orderId, photos: prepared, maxPhotos: MAX_PHOTOS });
    }

    if (action === "finalize") {
      const ids = Array.isArray(body.clientPhotoIds) ? body.clientPhotoIds.map((x: unknown) => String(x)).filter(validClientId) : [];
      if (!ids.length || ids.length > MAX_PHOTOS) return json(400, { ok: false, message: "완료할 사진정보가 없습니다." });
      const { data: rows, error: rowsError } = await admin.from("nova_houseman_order_photos").select("*").eq("order_id", orderId).in("client_photo_id", ids);
      if (rowsError) throw rowsError;
      const ready: any[] = [];
      for (const row of rows || []) {
        if (String(row.uploaded_by) !== String(authz.employeeNo || "")) return json(403, { ok: false, message: "사진 완료 소유권을 확인할 수 없습니다." });
        if (String(row.status) !== "READY") {
          const path = String(row.object_path || "");
          const cut = path.lastIndexOf("/");
          const dir = cut >= 0 ? path.slice(0, cut) : "";
          const name = cut >= 0 ? path.slice(cut + 1) : path;
          const { data: listed, error: listError } = await admin.storage.from(BUCKET).list(dir, { limit: 20, search: name });
          if (listError) throw listError;
          const object: any = (listed || []).find((item: any) => String(item.name) === name);
          if (!object) return json(409, { ok: false, message: "업로드된 사진 파일을 확인하지 못했습니다." });
          const size = Number(object.metadata?.size || row.size_bytes || 0);
          const { data: updated, error: updateError } = await admin.from("nova_houseman_order_photos").update({
            status: "READY",
            size_bytes: size,
            mime_type: "image/jpeg",
            uploaded_at: new Date().toISOString(),
          }).eq("photo_id", row.photo_id).select().single();
          if (updateError) throw updateError;
          row.status = updated.status;
          row.size_bytes = updated.size_bytes;
          row.uploaded_at = updated.uploaded_at;
        }
        ready.push({
          storage: "SUPABASE",
          photoId: row.photo_id,
          clientPhotoId: row.client_photo_id,
          fileId: `sb:${row.photo_id}`,
          objectPath: row.object_path,
          name: row.file_name,
          mimeType: row.mime_type,
          size: Number(row.size_bytes || 0),
          uploadedAt: row.uploaded_at || row.created_at,
          uploadedBy: row.uploaded_by,
        });
      }
      return json(200, { ok: true, orderId, photos: ready, photoCount: ready.length });
    }

    if (action === "thumbnail") {
      const photoId = String(body.photoId || "").trim().replace(/^sb:/, "");
      if (!/^[0-9a-f-]{36}$/i.test(photoId)) return json(400, { ok: false, message: "사진 식별값이 올바르지 않습니다." });
      const { data: row, error: rowError } = await admin.from("nova_houseman_order_photos").select("*").eq("order_id", orderId).eq("photo_id", photoId).eq("status", "READY").maybeSingle();
      if (rowError) throw rowError;
      if (!row) return json(404, { ok: false, message: "사진을 찾을 수 없습니다." });
      const { data: signed, error: signedError } = await admin.storage.from(BUCKET).createSignedUrl(String(row.object_path), 300, {
        transform: {
          width: THUMB_WIDTH,
          height: THUMB_HEIGHT,
          resize: "contain",
          quality: THUMB_QUALITY,
        },
      });
      if (signedError || !signed?.signedUrl) throw signedError || new Error("사진 썸네일 URL을 만들지 못했습니다.");
      return json(200, {
        ok: true,
        orderId,
        photo: {
          storage: "SUPABASE", photoId: row.photo_id, fileId: `sb:${row.photo_id}`,
          name: row.file_name, mimeType: row.mime_type, size: Number(row.size_bytes || 0), uploadedAt: row.uploaded_at || row.created_at,
        },
        signedUrl: signed.signedUrl,
        expiresIn: 300,
        thumbnail: true,
        width: THUMB_WIDTH,
        height: THUMB_HEIGHT,
        quality: THUMB_QUALITY,
      });
    }

    if (action === "view") {
      const photoId = String(body.photoId || "").trim().replace(/^sb:/, "");
      if (!/^[0-9a-f-]{36}$/i.test(photoId)) return json(400, { ok: false, message: "사진 식별값이 올바르지 않습니다." });
      const { data: row, error: rowError } = await admin.from("nova_houseman_order_photos").select("*").eq("order_id", orderId).eq("photo_id", photoId).eq("status", "READY").maybeSingle();
      if (rowError) throw rowError;
      if (!row) return json(404, { ok: false, message: "사진을 찾을 수 없습니다." });
      const { data: signed, error: signedError } = await admin.storage.from(BUCKET).createSignedUrl(String(row.object_path), 300);
      if (signedError || !signed?.signedUrl) throw signedError || new Error("사진 조회 URL을 만들지 못했습니다.");
      return json(200, {
        ok: true,
        orderId,
        photo: {
          storage: "SUPABASE", photoId: row.photo_id, fileId: `sb:${row.photo_id}`,
          name: row.file_name, mimeType: row.mime_type, size: Number(row.size_bytes || 0), uploadedAt: row.uploaded_at || row.created_at,
        },
        signedUrl: signed.signedUrl,
        expiresIn: 300,
      });
    }

    return json(400, { ok: false, message: "지원하지 않는 사진 작업입니다." });
  } catch (error) {
    console.error("nova-houseman-photo-v1", error);
    return json(500, { ok: false, message: error instanceof Error ? error.message : "사진 처리 중 오류가 발생했습니다." });
  }
});
