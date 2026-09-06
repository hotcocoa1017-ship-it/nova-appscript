import { createClient } from "npm:@supabase/supabase-js@2.57.0";
import { sendPushNotification, WebPushError } from "npm:@mmmike/web-push@1.3.0/send";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
// Hash only; the raw internal dispatch token is stored in Supabase Vault.
const TOKEN_SHA256 = "f5312c52debdc03e2129a2498c0e28afd0d33142650382df6844c001f90a965b";
const PWA_BASE = `${SUPABASE_URL}/storage/v1/object/public/nova-pwa-v2`;
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
  const bytes = new Uint8Array(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
  );
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function safeEqual(a: string, b: string) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function authorized(req: Request) {
  const token = String(req.headers.get("x-nova-web-push-token") || "").trim();
  if (token.length < 40) return false;
  return safeEqual(await sha256Text(token), TOKEN_SHA256);
}

function text(value: unknown) {
  return String(value ?? "").trim();
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ ok: false, code: "METHOD_NOT_ALLOWED" }, 405);
  if (!SUPABASE_URL || !SERVICE_ROLE_KEY) return json({ ok: false, code: "SERVER_CONFIG" }, 500);
  if (!(await authorized(req))) return json({ ok: false, code: "UNAUTHORIZED" }, 401);

  let body: any = {};
  try { body = await req.json(); } catch (_) {}
  const notificationId = Number(body?.notificationId || 0);
  if (!Number.isSafeInteger(notificationId) || notificationId <= 0) {
    return json({ ok: false, code: "INVALID_NOTIFICATION_ID" }, 400);
  }

  const { data: notification, error: notificationError } = await db
    .from("nova_notifications")
    .select("notification_id,recipient_employee_no,kind,title,body,site,room_no,entity_type,entity_id,priority,payload,created_at")
    .eq("notification_id", notificationId)
    .maybeSingle();
  if (notificationError) return json({ ok: false, code: "NOTIFICATION_LOOKUP_FAILED" }, 500);
  if (!notification) return json({ ok: false, code: "NOTIFICATION_NOT_FOUND" }, 404);

  const employeeNo = text(notification.recipient_employee_no);
  const { data: subscriptions, error: subscriptionError } = await db
    .from("nova_push_subscriptions")
    .select("subscription_id,endpoint,p256dh,auth_secret")
    .eq("employee_no", employeeNo)
    .eq("enabled", true);
  if (subscriptionError) return json({ ok: false, code: "SUBSCRIPTION_LOOKUP_FAILED" }, 500);
  const subs = Array.isArray(subscriptions) ? subscriptions : [];
  if (!subs.length) {
    return json({ ok: true, notificationId, delivered: 0, gone: 0, failed: 0, skipped: "NO_SUBSCRIPTIONS" });
  }

  const { data: vapid, error: vapidError } = await db.rpc("nova_web_push_config_service");
  if (vapidError || !vapid?.publicKey || !vapid?.privateKey || !vapid?.subject) {
    return json({ ok: false, code: "VAPID_CONFIG_FAILED" }, 500);
  }

  const { count: unreadCount } = await db
    .from("nova_notifications")
    .select("notification_id", { count: "exact", head: true })
    .eq("recipient_employee_no", employeeNo)
    .is("read_at", null);

  const sourcePayload = notification.payload && typeof notification.payload === "object"
    ? notification.payload
    : {};
  const route = text(sourcePayload.route);
  const site = text(sourcePayload.site || notification.site);
  const roomNo = text(sourcePayload.roomNo || notification.room_no);
  const params = new URLSearchParams();
  if (route) params.set("route", route);
  if (site) params.set("site", site);
  if (roomNo) params.set("roomNo", roomNo);
  params.set("notificationId", String(notificationId));
  const clickUrl = `${PWA_BASE}/index.html?${params.toString()}`;

  const payload = {
    title: text(notification.title) || "NOVA 알림",
    body: text(notification.body),
    icon: `${PWA_BASE}/icon-192.png`,
    badge: `${PWA_BASE}/badge-96.png`,
    tag: `nova-${notificationId}`,
    data: {
      url: clickUrl,
      route,
      site,
      roomNo,
      notificationId,
      badgeCount: Number(unreadCount || 0),
    },
    timestamp: Date.parse(String(notification.created_at || "")) || Date.now(),
    requireInteraction: text(notification.priority).toUpperCase() === "HIGH",
  };

  let delivered = 0;
  let gone = 0;
  let failed = 0;
  const errors: string[] = [];

  for (const sub of subs) {
    try {
      await sendPushNotification(
        {
          endpoint: text(sub.endpoint),
          keys: { p256dh: text(sub.p256dh), auth: text(sub.auth_secret) },
        },
        payload,
        {
          publicKey: text(vapid.publicKey),
          privateKey: text(vapid.privateKey),
          subject: text(vapid.subject),
        },
      );
      delivered++;
      await db.from("nova_push_subscriptions").update({
        last_success_at: new Date().toISOString(),
        failure_count: 0,
        last_error: "",
      }).eq("subscription_id", sub.subscription_id);
    } catch (error) {
      const status = error instanceof WebPushError
        ? Number(error.statusCode || 0)
        : Number((error as any)?.statusCode || 0);
      const message = text((error as any)?.message || error).slice(0, 300);
      if (status === 404 || status === 410) {
        gone++;
        await db.from("nova_push_subscriptions").update({
          enabled: false,
          last_failure_at: new Date().toISOString(),
          last_error: message,
        }).eq("subscription_id", sub.subscription_id);
      } else {
        failed++;
        errors.push(message);
        await db.from("nova_push_subscriptions").update({
          last_failure_at: new Date().toISOString(),
          failure_count: 1,
          last_error: message,
        }).eq("subscription_id", sub.subscription_id);
      }
    }
  }

  await db.from("nova_push_delivery_runs").insert({
    notification_id: notificationId,
    employee_no: employeeNo,
    completed_at: new Date().toISOString(),
    delivered,
    gone,
    failed,
    error_summary: errors.join(" | ").slice(0, 1200),
  });

  return json({ ok: failed === 0, notificationId, delivered, gone, failed });
});
