from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
room = (ROOT / '09_RoomStatusUpload.js').read_text(encoding='utf-8')
client = (ROOT / 'Client.html').read_text(encoding='utf-8')
rt = (ROOT / 'RealtimeDailySync.js').read_text(encoding='utf-8')
migration = (ROOT / 'supabase/migrations/20260910_room_upload_reliability_guard_v5.sql').read_text(encoding='utf-8')
lockdown = (ROOT / 'supabase/migrations/20260910_room_upload_legacy_rpc_lockdown_v1.sql').read_text(encoding='utf-8')

checks = {
    'room recovery ttl': 'ROOM_UPLOAD_RECOVERY_TTL_V1' in room and '24 * 60 * 60 * 1000' in room,
    'room forward hold': 'ROOM_UPLOAD_FORWARD_SYNC_HOLD_V1' in room and 'markRoomUploadDbCommittedHold' in room,
    'new date append': "roomWriteMode = 'APPEND_NEW_BLOCK'" in room,
    'no canonical full rewrite': 'ROOM_UPLOAD_MIRROR_FAIL_CLOSED_V1' in room,
    'mirror readback': 'ROOM_UPLOAD_MIRROR_READBACK_V1' in room and 'verifyRoomStatusUploadMirrorBlock_' in room,
    'hold cleared after mirror': 'clearRoomUploadRealtimeForwardHold_(plan.businessDate, plan.site)' in room,
    'realtime skips held site': 'ROOM_UPLOAD_DB_FIRST_MIRROR_PENDING' in rt and 'isRoomUploadRealtimeForwardHeld_' in rt,
    'client V5': "'nova_room_upload_apply_v5'" in client,
    'client no legacy fallback marker': client.count('ROOM_UPLOAD_NO_LEGACY_FALLBACK_V1') >= 2,
    'durable mirror recovery': 'ROOM_UPLOAD_DURABLE_MIRROR_RECOVERY_V1' in client and 'novaRoomUploadRecoverPendingMirror_' in client,
    'no reupload instruction': '같은 업로드 버튼을 다시' not in client and '다시 눌러 복구' not in client,
    'db committed UI': '후처리 자동복구 중 · 재업로드 금지' in client,
    'stage tracking': 'nova_room_upload_mark_stage_v1' in client,
    'V5 migration': 'nova_room_upload_apply_v5' in migration and 'room_upload_site_guard_v1' in migration,
    'V5 baseline set guard': '최근 정상 객실목록' in migration,
    'V5 count guard': 'expected_room_count' in migration and "('쏘라노', 755" in migration and "('별관', 798" in migration,
    'V5 stage columns': 'sheet_mirror_status' in migration and 'db_committed_at' in migration,
    'legacy V2 authenticated closed': 'nova_room_upload_apply_v2(text, text, jsonb, jsonb, bigint, bigint, text)' in lockdown and 'from public, anon, authenticated' in lockdown,
    'legacy V3 authenticated closed': 'nova_room_upload_apply_v3(text, text, jsonb, jsonb, bigint, bigint, text)' in lockdown and lockdown.count('from public, anon, authenticated') >= 2,
    'V4 compatibility retained': 'nova_room_upload_apply_v4' not in lockdown,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(('PASS' if ok else 'FAIL'), name)
if failed:
    raise SystemExit('ROOM_UPLOAD_RELIABILITY_V5 failed: ' + ', '.join(failed))
print(f'ROOM_UPLOAD_RELIABILITY_V5 PASS ({len(checks)}/{len(checks)})')
