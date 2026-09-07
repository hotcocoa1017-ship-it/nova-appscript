from pathlib import Path

MARKER = 'QM_CLEAR_SERVER_DB_FIRST_V1'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


indicator_path = Path('06_Indicator.js')
server_path = Path('RealtimeDbFirstServer.js')
mirror_path = Path('RealtimeDailySync.js')
client_path = Path('Client.html')

indicator = indicator_path.read_text(encoding='utf-8')
server = server_path.read_text(encoding='utf-8')
mirror = mirror_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')

all_applied = MARKER in indicator and MARKER in server and MARKER in mirror
if all_applied:
    print('QM clear server DB-first v1 already applied')
    raise SystemExit(0)

if MARKER not in indicator:
    branch_anchor = """    // QM 배정도 PostgreSQL을 원본으로 사용합니다. // QM_ASSIGN_SERVER_DB_FIRST_V1
"""
    branch = """    // QM 배정 초기화도 PostgreSQL을 원본으로 사용합니다. // QM_CLEAR_SERVER_DB_FIRST_V1
    // Realtime=Y이면 전용 보안 RPC가 QM 배정만 DB에서 먼저 초기화합니다.
    // 룸메이드 배정/청소완료 실적과 기존 QM 체크리스트·점검이력은 보존합니다.
    // 현재객실현황·QM 업무이력은 DB 이벤트 미러가 후행 처리합니다.
    if (action === 'QM_CLEAR'
        && typeof novaQmClearDbFirstEnabled_ === 'function'
        && novaQmClearDbFirstEnabled_()
        && typeof novaQmClearDbApply_ === 'function') {
      return clearIndicatorQmDbFirst_(token, user, safe, {
        startedMs,
        businessDate,
        site,
        roomNo
      });
    }

    // QM 배정도 PostgreSQL을 원본으로 사용합니다. // QM_ASSIGN_SERVER_DB_FIRST_V1
"""
    indicator = replace_once(indicator, branch_anchor, branch, 'QM clear branch')

    helper_anchor = "function assignIndicatorQmDbFirst_(token, user, payload, context) { // (QM 배정 PostgreSQL 원본 경로) // QM_ASSIGN_SERVER_DB_FIRST_V1\n"
    helper = """function clearIndicatorQmDbFirst_(token, user, payload, context) { // (QM 배정 초기화 PostgreSQL 원본 경로) // QM_CLEAR_SERVER_DB_FIRST_V1
  const safe = payload || {};
  const info = context || {};
  const businessDate = info.businessDate;
  const site = String(info.site || '').trim();
  const roomNo = String(info.roomNo || '').trim();
  const startedMs = Number(info.startedMs || Date.now());
  if (!site || !roomNo) throw new Error('QM 배정 초기화에 사업장과 객실번호가 필요합니다.');

  const requestId = String(safe.requestId || '').trim() || `QM_CLEAR:${Utilities.getUuid()}`;
  const expectedState = safe.expectedState && typeof safe.expectedState === 'object'
    ? Object.assign({}, safe.expectedState)
    : {};
  const dbResult = novaQmClearDbApply_(token, {
    businessDate,
    site,
    roomNo,
    requestId
  });
  if (!dbResult || dbResult.ok === false) {
    const error = new Error(String(dbResult && (dbResult.message || dbResult.code) || 'QM 배정 초기화 DB 저장에 실패했습니다.'));
    error.code = String(dbResult && dbResult.code || 'QM_CLEAR_DB_WRITE_FAILED');
    throw error;
  }

  const dbRoom = dbResult.room && typeof dbResult.room === 'object' ? dbResult.room : {};
  const version = Number(dbResult.version || dbRoom.version || 0);
  const finishedMs = Date.now();
  return {
    ok: true,
    dbFirst: true,
    alreadySet: Boolean(dbResult.idempotent),
    version,
    requestId: String(dbResult.requestId || requestId),
    previousQmEmployeeNo: String(dbResult.previousQmEmployeeNo || expectedState.qmEmployeeNo || ''),
    room: {
      rowNumber: Number(safe.rowNumber || 0),
      businessDate: String(dbRoom.businessDate || businessDate),
      site: String(dbRoom.site || site),
      roomNo: String(dbRoom.roomNo || roomNo),
      roomStatus: String(dbRoom.roomStatus || expectedState.roomStatus || ''),
      cleaningStatus: String(dbRoom.cleaningStatus || dbResult.cleaningStatus || 'COMPLETED'),
      cleaningType: String(dbRoom.cleaningType || expectedState.cleaningType || ''),
      assignmentType: String(dbRoom.assignmentType || expectedState.assignmentType || ''),
      roommaidEmployeeNo: String(dbRoom.roommaidEmployeeNo || expectedState.roommaidEmployeeNo || ''),
      secondaryRoommaidEmployeeNo: String(dbRoom.secondaryRoommaidEmployeeNo || expectedState.secondaryRoommaidEmployeeNo || ''),
      qmEmployeeNo: '',
      operationalStatus: String(dbRoom.operationalStatus || expectedState.operationalStatus || ''),
      updatedAt: String(dbRoom.updatedAt || ''),
      version
    },
    mirrorPending: true,
    notificationQueued: false,
    notificationDeferred: false,
    deferredNotification: null,
    timing: {
      qmClear: true,
      dbFirst: true,
      totalMs: Math.max(0, finishedMs - startedMs)
    }
  };
}

"""
    indicator = replace_once(indicator, helper_anchor, helper + helper_anchor, 'QM clear helper')

if MARKER not in server:
    server_anchor = "function novaQmInspectionDbFirstEnabled_() { // QM_INSPECTION_FINALIZE_DB_FIRST_V1\n"
    server_helper = """function novaQmClearDbFirstEnabled_() { // QM_CLEAR_SERVER_DB_FIRST_V1
  const props = PropertiesService.getScriptProperties();
  if (String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase() !== 'Y') return false;
  return String(props.getProperty('NOVA_QM_CLEAR_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N';
}

function novaQmClearDbApply_(token, payload) { // QM_CLEAR_SERVER_DB_FIRST_V1
  const safe = payload || {};
  return novaRealtimeUserRpc_(token, 'nova_qm_clear_v1', {
    p_business_date: String(safe.businessDate || '').trim(),
    p_site: String(safe.site || '').trim(),
    p_room_no: String(safe.roomNo || '').trim(),
    p_request_id: String(safe.requestId || '').trim()
  });
}

"""
    server = replace_once(server, server_anchor, server_helper + server_anchor, 'QM clear RPC bridge')

if MARKER not in mirror:
    mirror_anchor = "      if (action === 'QM_ASSIGN') {\n"
    mirror_branch = """      if (action === 'QM_CLEAR') { // QM_CLEAR_SERVER_DB_FIRST_V1
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const previousQmNo = String(
          eventDetail.previousQmEmployeeNo || rowInfo.data['QM사번'] || ''
        ).trim();
        const previousCleaningStatus = String(
          eventDetail.previousCleaningStatus || rowInfo.data['청소상태'] || ''
        ).trim().toUpperCase();
        const nextCleaningStatus = String(
          event.afterStatus || eventDetail.cleaningStatus || previousCleaningStatus || 'COMPLETED'
        ).trim().toUpperCase();

        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: nextCleaningStatus,
          qmEmployeeNo: '',
          version,
          updatedAt: nowText_()
        });
        rowInfo.data['청소상태'] = nextCleaningStatus;
        rowInfo.data['QM사번'] = '';

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: previousQmNo,
          status: 'QM_CLEAR',
          detail: {
            requestId,
            realtime: true,
            action: 'QM_CLEAR',
            role: String(eventDetail.role || 'ORDER').trim().toUpperCase(),
            previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            previousCleaningStatus,
            cleaningStatus: nextCleaningStatus,
            cleaningType,
            assignmentType,
            primaryEmployeeNo: roommaidNo,
            secondaryEmployeeNo: secondaryRoommaidNo,
            previousQmEmployeeNo: previousQmNo,
            qmEmployeeNo: '',
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      if (action === 'QM_ASSIGN') {
"""
    mirror = replace_once(mirror, mirror_anchor, mirror_branch, 'QM clear event mirror')

required_indicator = [
    MARKER,
    "if (action === 'QM_CLEAR'",
    'clearIndicatorQmDbFirst_',
    'novaQmClearDbApply_',
    "qmEmployeeNo: ''",
    'mirrorPending: true'
]
required_server = [MARKER, 'novaQmClearDbFirstEnabled_', "'nova_qm_clear_v1'", 'NOVA_QM_CLEAR_DB_FIRST_ENABLED']
required_mirror = [MARKER, "if (action === 'QM_CLEAR')", "status: 'QM_CLEAR'", 'previousQmEmployeeNo: previousQmNo']
for label, body, needles in [
    ('06_Indicator.js', indicator, required_indicator),
    ('RealtimeDbFirstServer.js', server, required_server),
    ('RealtimeDailySync.js', mirror, required_mirror)
]:
    missing = [needle for needle in needles if needle not in body]
    if missing:
        raise SystemExit(f'{label} validation failed: {missing}')

# QM_CLEAR는 Cloud Run 직통 액션 목록에 넣지 않습니다. 전용 Supabase RPC를 쓰는 서버 경로가 원본입니다.
realtime_pos = client.find('const realtimeAction =')
if realtime_pos >= 0:
    realtime_end = client.find(';', realtime_pos)
    direct_block = client[realtime_pos:realtime_end]
    if "'QM_CLEAR'" in direct_block:
        raise SystemExit('Client realtime direct list must not route QM_CLEAR to Cloud Run')

indicator_path.write_text(indicator, encoding='utf-8')
server_path.write_text(server, encoding='utf-8')
mirror_path.write_text(mirror, encoding='utf-8')
print('patched QM clear server DB-first v1')
