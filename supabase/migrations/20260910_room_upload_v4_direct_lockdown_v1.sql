-- ROOM_UPLOAD_V4_DIRECT_LOCKDOWN_V1
-- V5 is the only authenticated browser mutation entry point.
-- V5 is SECURITY DEFINER owned by postgres and continues to delegate internally to V4.
-- Revoking authenticated/public/anon direct V4 execution prevents stale clients from bypassing V5 guards.

revoke execute on function public.nova_room_upload_apply_v4(text, text, jsonb, jsonb, jsonb, bigint, text)
  from public, anon, authenticated;
