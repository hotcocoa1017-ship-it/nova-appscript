from pathlib import Path

MARKER = 'ROOM_OPERATION_FLAGS_DB_FIRST_V1'


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)

# 1) Server RPC bridge: room-upload V3/V2 + dedicated operation-flags RPC.
bridge_path = Path('RealtimeDbFirstServer.js')
bridge = bridge_path.read_text(encoding='utf-8')
bridge = bridge.replace("'nova_room_upload_state_v1'", "'nova_room_upload_state_v2'", 1)
bridge = bridge.replace("'nova_room_upload_apply_v2'", "'nova_room_upload_apply_v3'", 1)
if MARKER not in bridge:
    anchor = "function novaQmClearDbFirstEnabled_() { // QM_CLEAR_SERVER_DB_FIRST_V1"
    helper = """function novaRoomOperationFlagsDbFirstEnabled_() { // ROOM_OPERATION_FLAGS_DB_FIRST_V1\n  const props = PropertiesService.getScriptProperties();\n  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;\n  return String(props.getProperty('NOVA_ROOM_OPERATION_FLAGS_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';\n}\n\nfunction novaRoomOperationFlagsDbApply_(token, payload) { // ROOM_OPERATION_FLAGS_DB_FIRST_V1\n  const safe = payload || {};\n  return novaRealtimeUserRpc_(token, 'nova_room_operation_flags_update_v1', {\n    p_business_date: String(safe.businessDate || '').trim(),\n    p_site: String(safe.site || '').trim(),\n    p_room_no: String(safe.roomNo || '').trim(),\n    p_preassigned: Boolean(safe.preassigned),\n    p_vip: Boolean(safe.vip),\n    p_important_room: Boolean(safe.importantRoom),\n    p_request_id: String(safe.requestId || '').trim()\n  });\n}\n\n"""
    if anchor not in bridge:
        raise SystemExit('RealtimeDbFirstServer helper insertion anchor not found')
    bridge = bridge.replace(anchor, helper + anchor, 1)
bridge_path.write_text(bridge, encoding='utf-8')

# 2) Indicator server entry: DB first when enabled; Sheet switch remains kill-switch fallback.
indicator_path = Path('06_Indicator.js')
indicator = indicator_path.read_text(encoding='utf-8')
if MARKER not in indicator:
    anchor = "    // 고장·객실확인은 사용자 전체 인덱스·일반 작업분기 로딩을 건너뛰고 핵심 저장만 수행한다."
    guard = """    // 선배정/VIP/중요객실도 PostgreSQL 현재상태를 원본으로 사용합니다. // ROOM_OPERATION_FLAGS_DB_FIRST_V1\n    // DB 확정 후 현재객실현황·업무이력은 기존 DB 이벤트 미러가 후행 반영합니다.\n    if (action === 'UPDATE_OPERATION_FLAGS'\n        && typeof novaRoomOperationFlagsDbFirstEnabled_ === 'function'\n        && novaRoomOperationFlagsDbFirstEnabled_()\n        && typeof novaRoomOperationFlagsDbApply_ === 'function') {\n      return updateIndicatorRoomOperationFlagsDbFirst_(token, user, safe, {\n        startedMs,\n        businessDate,\n        site,\n        roomNo\n      });\n    }\n\n"""
    if anchor not in indicator:
        raise SystemExit('06_Indicator DB-first guard anchor not found')
    indicator = indicator.replace(anchor, guard + anchor, 1)

    helper = """\nfunction updateIndicatorRoomOperationFlagsDbFirst_(token, user, payload, context) { // ROOM_OPERATION_FLAGS_DB_FIRST_V1\n  const safe = payload || {};\n  const info = context || {};\n  const businessDate = info.businessDate;\n  const site = String(info.site || '').trim();\n  const roomNo = String(info.roomNo || '').trim();\n  const startedMs = Number(info.startedMs || Date.now());\n  if (!site || !roomNo) throw new Error('운영표시 저장에 사업장과 객실번호가 필요합니다.');\n\n  const requestId = String(safe.requestId || '').trim() || `ROOM_FLAGS:${Utilities.getUuid()}`;\n  const dbResult = novaRoomOperationFlagsDbApply_(token, {\n    businessDate,\n    site,\n    roomNo,\n    preassigned: Boolean(safe.preassigned),\n    vip: Boolean(safe.vip),\n    importantRoom: Boolean(safe.importantRoom),\n    requestId\n  });\n  if (!dbResult || dbResult.ok === false) throw new Error(String(dbResult && dbResult.message || '객실 운영표시를 DB에 저장하지 못했습니다.'));\n\n  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};\n  const version = Number(dbResult.version || dbRoom.version || 0);\n  const finishedMs = Date.now();\n  return {\n    ok: true,\n    dbFirst: true,\n    alreadySet: Boolean(dbResult.idempotent || dbResult.alreadySet),\n    version,\n    requestId: String(dbResult.requestId || requestId),\n    room: {\n      rowNumber: Number(safe.rowNumber || 0),\n      businessDate: String(dbRoom.businessDate || businessDate),\n      site: String(dbRoom.site || site),\n      roomNo: String(dbRoom.roomNo || roomNo),\n      roomStatus: String(dbRoom.roomStatus || ''),\n      cleaningStatus: String(dbRoom.cleaningStatus || ''),\n      cleaningType: String(dbRoom.cleaningType || ''),\n      assignmentType: String(dbRoom.assignmentType || ''),\n      roommaidEmployeeNo: String(dbRoom.roommaidEmployeeNo || ''),\n      secondaryRoommaidEmployeeNo: String(dbRoom.secondaryRoommaidEmployeeNo || ''),\n      qmEmployeeNo: String(dbRoom.qmEmployeeNo || ''),\n      operationalStatus: String(dbRoom.operationalStatus || ''),\n      preassigned: Boolean(dbRoom.preassigned),\n      vip: Boolean(dbRoom.vip),\n      importantRoom: Boolean(dbRoom.importantRoom),\n      updatedAt: String(dbRoom.updatedAt || ''),\n      version\n    },\n    mirrorPending: true,\n    notificationQueued: false,\n    notificationDeferred: false,\n    deferredNotification: null,\n    timing: { operationFlags: true, dbFirst: true, totalMs: Math.max(0, finishedMs - startedMs) }\n  };\n}\n"""
    indicator += helper
indicator_path.write_text(indicator, encoding='utf-8')

# 3) Room upload: DB snapshot includes flags; merge preserves them, reset clears them; DB payload sends them.
upload_path = Path('09_RoomStatusUpload.js')
upload = upload_path.read_text(encoding='utf-8')
if MARKER not in upload:
    old = """            '객실운영상태': String(data['객실운영상태'] || '').trim(),\n            '마지막변경버전': Number(data['마지막변경버전'] || 0),"""
    new = """            '객실운영상태': String(data['객실운영상태'] || '').trim(),\n            '선배정여부': normalizeYesNo_(data['선배정여부']) === 'Y' ? 'Y' : 'N', // ROOM_OPERATION_FLAGS_DB_FIRST_V1\n            'VIP여부': normalizeYesNo_(data['VIP여부']) === 'Y' ? 'Y' : 'N',\n            '중요객실여부': normalizeYesNo_(data['중요객실여부']) === 'Y' ? 'Y' : 'N',\n            '마지막변경버전': Number(data['마지막변경버전'] || 0),"""
    upload = replace_once(upload, old, new, 'DB current flag merge')

    old = """          'QM사번': operation.qmEmployeeNo,\n          '마지막변경버전': version,"""
    new = """          'QM사번': operation.qmEmployeeNo,\n          '선배정여부': resetExisting ? 'N' : (normalizeYesNo_(existingRoom['선배정여부']) === 'Y' ? 'Y' : 'N'), // ROOM_OPERATION_FLAGS_DB_FIRST_V1\n          'VIP여부': resetExisting ? 'N' : (normalizeYesNo_(existingRoom['VIP여부']) === 'Y' ? 'Y' : 'N'),\n          '중요객실여부': resetExisting ? 'N' : (normalizeYesNo_(existingRoom['중요객실여부']) === 'Y' ? 'Y' : 'N'),\n          '마지막변경버전': version,"""
    upload = replace_once(upload, old, new, 'upload row flag preservation')

    old = """      qmEmployeeNo: String(data['QM사번'] || '').trim(),\n      operationalStatus: typeof normalizeIndicatorRoomOperationalStatus_ === 'function'"""
    new = """      qmEmployeeNo: String(data['QM사번'] || '').trim(),\n      preassigned: normalizeYesNo_(data['선배정여부']) === 'Y', // ROOM_OPERATION_FLAGS_DB_FIRST_V1\n      vip: normalizeYesNo_(data['VIP여부']) === 'Y',\n      importantRoom: normalizeYesNo_(data['중요객실여부']) === 'Y',\n      operationalStatus: typeof normalizeIndicatorRoomOperationalStatus_ === 'function'"""
    upload = replace_once(upload, old, new, 'DB payload flag mapping')
upload_path.write_text(upload, encoding='utf-8')

# 4) Client: route UPDATE_OPERATION_FLAGS through Apps Script server so dedicated secured RPC owns the write.
client_path = Path('Client.html')
client = client_path.read_text(encoding='utf-8')
old_token = "'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'"
new_token = "'UPDATE_ROOM_OPERATION_STATUS', 'CLEAR_ASSIGNMENT' // ROOM_OPERATION_FLAGS_DB_FIRST_V1: server RPC owns flag mutation"
if old_token in client:
    client = client.replace(old_token, new_token, 1)
elif 'ROOM_OPERATION_FLAGS_DB_FIRST_V1: server RPC owns flag mutation' not in client:
    raise SystemExit('Client realtimeAction operation-flags anchor not found')
client_path.write_text(client, encoding='utf-8')

# Final structural assertions.
bridge = bridge_path.read_text(encoding='utf-8')
indicator = indicator_path.read_text(encoding='utf-8')
upload = upload_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')
for label, body, required in [
    ('RealtimeDbFirstServer.js', bridge, [MARKER, 'nova_room_operation_flags_update_v1', 'nova_room_upload_state_v2', 'nova_room_upload_apply_v3']),
    ('06_Indicator.js', indicator, [MARKER, 'updateIndicatorRoomOperationFlagsDbFirst_', 'novaRoomOperationFlagsDbApply_']),
    ('09_RoomStatusUpload.js', upload, [MARKER, "'선배정여부': resetExisting ? 'N'", 'importantRoom: normalizeYesNo_']),
    ('Client.html', client, [MARKER + ': server RPC owns flag mutation'])
]:
    missing = [value for value in required if value not in body]
    if missing:
        raise SystemExit(f'{label} validation failed: {missing}')

print('room operation flags DB-first patch OK')
