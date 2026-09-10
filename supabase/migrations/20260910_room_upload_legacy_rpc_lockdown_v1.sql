-- ROOM_UPLOAD_LEGACY_RPC_LOCKDOWN_V1
-- V5 is the canonical guarded upload endpoint. V4 remains callable because V5 delegates
-- to it and it is retained for short-lived compatibility. V2/V3 must not remain reachable
-- from authenticated browser sessions because they predate the V5 payload/site safeguards.

revoke execute on function public.nova_room_upload_apply_v2(text, text, jsonb, jsonb, bigint, bigint, text)
  from public, anon, authenticated;

revoke execute on function public.nova_room_upload_apply_v3(text, text, jsonb, jsonb, bigint, bigint, text)
  from public, anon, authenticated;
