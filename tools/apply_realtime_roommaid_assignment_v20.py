#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
CLIENT = REPO / 'Client.html'
SYNC = REPO / 'RealtimeDailySync.js'
CLOUD = Path.home() / 'nova-realtime' / 'cloud-run' / 'index.js'


def fail(msg):
    print(f'PATCH_ERROR: {msg}')
    sys.exit(1)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


def backup(path, suffix):
    out = path.with_name(path.name + suffix)
    if not out.exists():
        out.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
    return out

for p in (CLIENT, SYNC, CLOUD):
    if not p.exists():
        fail(f'file not found: {p}')

# -----------------------------------------------------------------------------
# Client: route ASSIGN_ROOMMAID through existing Realtime room action endpoint.
# Existing optimistic UI remains unchanged. Sheets/history are mirrored by the
# existing 1-minute DB->Sheets mirror, extended below for assignment events.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')
client_original = client
client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE'].includes(mappedAction);",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID'].includes(mappedAction);",
    'Client realtime action list'
)
client = replace_once(
    client,
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : '청소완료 처리했습니다.');",
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : '청소완료 처리했습니다.');",
    'Client realtime result message'
)

# -----------------------------------------------------------------------------
# RealtimeDailySync: mirror ASSIGN_ROOMMAID event to Sheets/history/Telegram.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
sync_original = sync
sync = replace_once(
    sync,
    "  const qmNotifications = [];\n",
    "  const qmNotifications = [];\n  const assignmentNotifications = [];\n",
    'assignment notification array'
)
sync = replace_once(
    sync,
    "      const action = String(event.action || '').trim().toUpperCase();\n      const cleaningType = String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();\n      const assignmentType = String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();\n      const roommaidNo = String(rowInfo.data['룸메이드사번'] || '').trim();\n      const secondaryRoommaidNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();",
    "      const action = String(event.action || '').trim().toUpperCase();\n      const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};\n      const cleaningType = String(action === 'ASSIGN_ROOMMAID' ? (eventDetail.cleaningType || NOVA.CLEANING_TYPES.NORMAL) : (rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL)).trim().toUpperCase();\n      const assignmentType = String(action === 'ASSIGN_ROOMMAID' ? (eventDetail.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO) : (rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO)).trim().toUpperCase();\n      const roommaidNo = String(action === 'ASSIGN_ROOMMAID' ? eventDetail.primaryEmployeeNo : (rowInfo.data['룸메이드사번'] || '')).trim();\n      const secondaryRoommaidNo = String(action === 'ASSIGN_ROOMMAID' ? eventDetail.secondaryEmployeeNo : (rowInfo.data['보조룸메이드사번'] || '')).trim();",
    'assignment event fields'
)
sync = replace_once(
    sync,
    "      roomUpdates.push({\n        rowNumber: rowInfo.rowNumber,\n        cleaningStatus: afterStatus,\n        version,\n        updatedAt: nowText_()\n      });\n      // 같은 배치에서 같은 객실 후속 이벤트가 오면 다음 이벤트가 갱신상태를 보도록 메모리도 즉시 갱신한다.\n      rowInfo.data['청소상태'] = afterStatus;",
    "      roomUpdates.push({\n        rowNumber: rowInfo.rowNumber,\n        cleaningStatus: afterStatus,\n        cleaningType,\n        assignmentType,\n        roommaidEmployeeNo: roommaidNo,\n        secondaryRoommaidEmployeeNo: secondaryRoommaidNo,\n        version,\n        updatedAt: nowText_()\n      });\n      // 같은 배치에서 같은 객실 후속 이벤트가 오면 다음 이벤트가 갱신상태를 보도록 메모리도 즉시 갱신한다.\n      rowInfo.data['청소상태'] = afterStatus;\n      if (action === 'ASSIGN_ROOMMAID') {\n        rowInfo.data['정비유형'] = cleaningType;\n        rowInfo.data['배정유형'] = assignmentType;\n        rowInfo.data['룸메이드사번'] = roommaidNo;\n        rowInfo.data['보조룸메이드사번'] = secondaryRoommaidNo;\n      }",
    'assignment room update payload'
)
sync = replace_once(
    sync,
    "        targetEmployeeNo: employeeNo,\n        status: action === 'CLEANING_START' ? 'ROOMMAID_START' : 'ROOMMAID_COMPLETE',\n        detail: {\n          requestId,\n          realtime: true,\n          action: action === 'CLEANING_START' ? 'START' : 'COMPLETE',\n          role: 'ROOMMAID',",
    "        targetEmployeeNo: action === 'ASSIGN_ROOMMAID' ? roommaidNo : employeeNo,\n        status: action === 'ASSIGN_ROOMMAID' ? 'ASSIGN_ROOMMAID' : (action === 'CLEANING_START' ? 'ROOMMAID_START' : 'ROOMMAID_COMPLETE'),\n        detail: {\n          requestId,\n          realtime: true,\n          action: action === 'ASSIGN_ROOMMAID' ? 'ASSIGN_ROOMMAID' : (action === 'CLEANING_START' ? 'START' : 'COMPLETE'),\n          role: action === 'ASSIGN_ROOMMAID' ? String(eventDetail.role || 'ORDER').trim().toUpperCase() : 'ROOMMAID',",
    'assignment history mapping'
)
anchor = """      if (action === 'CLEANING_COMPLETE' && afterStatus === 'QM_WAITING' && qmNo && usersByEmployeeNo[qmNo]) {
        qmNotifications.push({
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetUser: usersByEmployeeNo[qmNo],
          preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
          vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
          importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
          registeredBy: employeeNo,
          version
        });
      }
"""
insert = anchor + """
      if (action === 'ASSIGN_ROOMMAID') {
        const telegramBase = {
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
          cleaningType,
          cleaningStatus: afterStatus,
          assignmentType,
          preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
          vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
          importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
          registeredBy: employeeNo,
          version
        };
        if (roommaidNo && usersByEmployeeNo[roommaidNo]) {
          assignmentNotifications.push(Object.assign({}, telegramBase, {
            targetUser: usersByEmployeeNo[roommaidNo], assignmentRole: 'PRIMARY'
          }));
        }
        if (secondaryRoommaidNo && usersByEmployeeNo[secondaryRoommaidNo]) {
          assignmentNotifications.push(Object.assign({}, telegramBase, {
            targetUser: usersByEmployeeNo[secondaryRoommaidNo], assignmentRole: 'SECONDARY'
          }));
        }
      }
"""
sync = replace_once(sync, anchor, insert, 'assignment Telegram mirror')
sync = replace_once(
    sync,
    "    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));",
    "    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));\n    assignmentNotifications.forEach(payload => queueCleaningAssignmentTelegram_(payload));",
    'assignment Telegram dispatch'
)

batch_start = sync.find("function novaRealtimeFinalBatchUpdateCurrentRows_(sheet, updates) {")
batch_end = sync.find("function novaRealtimeFinalAppendHistoryBatch_(payloads) {", batch_start)
if batch_start < 0 or batch_end < 0:
    fail('RealtimeDailySync batch update function markers not found')
new_batch = """function novaRealtimeFinalBatchUpdateCurrentRows_(sheet, updates) { // (Realtime 객실상태·배정·버전 일괄기록)
  if (!updates.length) return;
  const headerMap = getHeaderMap_(sheet);
  const columns = {
    cleaningStatus: Number(headerMap['청소상태'] || 0),
    cleaningType: Number(headerMap['정비유형'] || 0),
    assignmentType: Number(headerMap['배정유형'] || 0),
    roommaidEmployeeNo: Number(headerMap['룸메이드사번'] || 0),
    secondaryRoommaidEmployeeNo: Number(headerMap['보조룸메이드사번'] || 0),
    version: Number(headerMap['마지막변경버전'] || 0),
    updatedAt: Number(headerMap['수정일시'] || 0)
  };
  if (Object.values(columns).some(value => !value)) {
    throw new Error('현재객실현황 Realtime 반영 열을 찾을 수 없습니다.');
  }

  const latestByRow = new Map();
  updates.forEach(item => latestByRow.set(Number(item.rowNumber), item));
  const rows = Array.from(latestByRow.keys()).filter(row => row >= 2).sort((a, b) => a - b);
  if (!rows.length) return;
  const firstRow = rows[0];
  const lastRow = rows[rows.length - 1];
  const count = lastRow - firstRow + 1;

  const valuesByKey = {};
  Object.entries(columns).forEach(([key, column]) => {
    valuesByKey[key] = sheet.getRange(firstRow, column, count, 1).getValues();
  });
  rows.forEach(rowNumber => {
    const item = latestByRow.get(rowNumber);
    const offset = rowNumber - firstRow;
    Object.keys(columns).forEach(key => {
      if (Object.prototype.hasOwnProperty.call(item, key)) valuesByKey[key][offset][0] = item[key];
    });
  });
  Object.entries(columns).forEach(([key, column]) => {
    sheet.getRange(firstRow, column, count, 1).setValues(valuesByKey[key]);
  });
}

"""
sync = sync[:batch_start] + new_batch + sync[batch_end:]

# -----------------------------------------------------------------------------
# Cloud Run: replace room action endpoint with v3.8-compatible endpoint that
# additionally supports ADMIN/ORDER ASSIGN_ROOMMAID.
# -----------------------------------------------------------------------------
cloud = CLOUD.read_text(encoding='utf-8')
cloud_original = cloud
route_start = cloud.find("app.post('/v1/rooms/:roomNo/action', async (req, res, next) => {")
route_end = cloud.find("\n\n/**\n * 하우스맨 오더 Realtime 선등록.", route_start)
if route_start < 0 or route_end < 0:
    fail('Cloud Run room action route markers not found')
new_route = r'''app.post('/v1/rooms/:roomNo/action', async (req, res, next) => {
  const startedAt = Date.now();
  let client;
  try {
    client = await pool.connect();
    const auth = authBearer(req);
    const body = req.body || {};
    const businessDate = String(body.businessDate || '').trim();
    const site = String(body.site || '').trim();
    const roomNo = String(req.params.roomNo || '').trim();
    const action = String(body.action || '').trim().toUpperCase();
    const requestId = String(body.requestId || req.headers['x-request-id'] || '').trim();
    const expectedVersion = Number(body.expectedVersion || 0);

    if (!businessDate || !site || !roomNo || !requestId) {
      throw httpError(400, 'INVALID_REQUEST', '업무일자·사업장·객실번호·requestId가 필요합니다.');
    }
    if (!['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID'].includes(action)) {
      throw httpError(400, 'INVALID_ACTION', '지원하지 않는 객실 작업입니다.');
    }

    await client.query('begin');
    const user = await loadUser(client, auth.employeeNo);
    if (!allowedForSite(user, site)) throw httpError(403, 'FORBIDDEN', '해당 사업장 처리 권한이 없습니다.');

    const inserted = await client.query(
      `insert into public.nova_request_dedup(request_id,employee_no,action)
       values($1,$2,$3) on conflict(request_id) do nothing returning request_id`,
      [requestId, user.employee_no, action]
    );
    if (!inserted.rowCount) {
      const prior = await client.query(`select response_json from public.nova_request_dedup where request_id=$1`, [requestId]);
      await client.query('commit');
      if (prior.rows[0]?.response_json) {
        return res.json({ ...prior.rows[0].response_json, duplicateRequest: true });
      }
      throw httpError(409, 'REQUEST_IN_PROGRESS', '동일 요청이 처리 중입니다.');
    }

    const found = await client.query(
      `select * from public.nova_rooms_current
        where business_date=$1 and site=$2 and room_no=$3 for update`,
      [businessDate, site, roomNo]
    );
    const room = found.rows[0];
    if (!room) throw httpError(404, 'ROOM_NOT_FOUND', '객실을 찾을 수 없습니다.');

    if (action === 'ASSIGN_ROOMMAID') {
      if (!['ADMIN', 'ORDER'].includes(user.role)) {
        throw httpError(403, 'FORBIDDEN', '룸메이드 배정 권한이 없습니다.');
      }
      if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
        throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
          currentRoom: roomDto(room)
        });
      }

      const primaryEmployeeNo = cleanText_(body.employeeNo, 80);
      const secondaryEmployeeNo = cleanText_(body.secondaryEmployeeNo, 80);
      const assignmentType = cleanText_(body.assignmentType || 'SOLO', 40).toUpperCase();
      const cleaningType = cleanText_(body.cleaningType || 'NORMAL', 40).toUpperCase();
      if (!primaryEmployeeNo) throw httpError(400, 'ROOMMAID_REQUIRED', '주담당 룸메이드를 선택하세요.');
      if (!['SOLO', 'PAIR', 'PAIR_TRAINING'].includes(assignmentType)) {
        throw httpError(400, 'INVALID_ASSIGNMENT_TYPE', '지원하지 않는 룸메이드 배정유형입니다.');
      }
      const pair = assignmentType === 'PAIR' || assignmentType === 'PAIR_TRAINING';
      if (pair && !secondaryEmployeeNo) throw httpError(400, 'SECONDARY_ROOMMAID_REQUIRED', '보조 룸메이드를 선택하세요.');
      if (!pair && secondaryEmployeeNo) throw httpError(400, 'INVALID_SECONDARY_ROOMMAID', '1인 배정에는 보조 룸메이드를 지정할 수 없습니다.');
      if (primaryEmployeeNo === secondaryEmployeeNo && secondaryEmployeeNo) {
        throw httpError(400, 'DUPLICATE_ROOMMAID', '주담당과 보조 룸메이드는 서로 달라야 합니다.');
      }

      const employeeNos = pair ? [primaryEmployeeNo, secondaryEmployeeNo] : [primaryEmployeeNo];
      const staff = await client.query(
        `select employee_no,name,role,enabled from public.nova_users where employee_no = any($1::text[])`,
        [employeeNos]
      );
      const staffByNo = Object.fromEntries(staff.rows.map(item => [String(item.employee_no), item]));
      const primary = staffByNo[primaryEmployeeNo];
      const secondary = secondaryEmployeeNo ? staffByNo[secondaryEmployeeNo] : null;
      if (!primary || !primary.enabled || String(primary.role || '').toUpperCase() !== 'ROOMMAID') {
        throw httpError(400, 'ROOMMAID_NOT_AVAILABLE', '주담당 룸메이드 정보를 확인할 수 없습니다.');
      }
      if (pair && (!secondary || !secondary.enabled || String(secondary.role || '').toUpperCase() !== 'ROOMMAID')) {
        throw httpError(400, 'ROOMMAID_NOT_AVAILABLE', '보조 룸메이드 정보를 확인할 수 없습니다.');
      }

      const sameAssignment = String(room.cleaning_status || '') === 'ASSIGNED'
        && String(room.cleaning_type || 'NORMAL') === cleaningType
        && String(room.assignment_type || 'SOLO') === assignmentType
        && String(room.roommaid_employee_no || '') === primaryEmployeeNo
        && String(room.secondary_roommaid_employee_no || '') === (secondaryEmployeeNo || '');
      if (sameAssignment) {
        const response = {
          ok: true, action, requestId, idempotent: true,
          room: roomDto(room), version: Number(room.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }

      const before = String(room.cleaning_status || '');
      const updated = await client.query(
        `update public.nova_rooms_current
            set cleaning_status='ASSIGNED',
                cleaning_type=$4,
                assignment_type=$5,
                roommaid_employee_no=$6,
                secondary_roommaid_employee_no=nullif($7,''),
                version=version+1,
                updated_by=$8,
                updated_at=now()
          where business_date=$1 and site=$2 and room_no=$3
          returning *`,
        [businessDate, site, roomNo, cleaningType, assignmentType, primaryEmployeeNo, secondaryEmployeeNo || '', user.employee_no]
      );
      const nextRoom = updated.rows[0];
      const detail = {
        source: 'NOVA_REALTIME',
        role: user.role,
        cleaningType,
        assignmentType,
        primaryEmployeeNo,
        primaryName: String(primary.name || ''),
        secondaryEmployeeNo: secondaryEmployeeNo || '',
        secondaryName: secondary ? String(secondary.name || '') : ''
      };
      await client.query(
        `insert into public.nova_room_events(
          request_id,business_date,site,room_no,action,before_status,after_status,
          employee_no,room_version,detail
        ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
        [requestId, businessDate, site, roomNo, action, before, 'ASSIGNED', user.employee_no, nextRoom.version, JSON.stringify(detail)]
      );
      const response = {
        ok: true, action, requestId,
        room: roomDto(nextRoom), version: Number(nextRoom.version || 0),
        timing: { totalMs: Date.now() - startedAt }
      };
      await client.query(
        `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
        [requestId, JSON.stringify(response)]
      );
      await client.query('commit');
      return res.json(response);
    }

    if (!canCleanRoom(user, room)) throw httpError(403, 'FORBIDDEN', '이 객실의 청소 처리 권한이 없습니다.');

    const hasQmHint = Object.prototype.hasOwnProperty.call(body, 'qmEmployeeNo');
    const qmEmployeeNo = hasQmHint ? cleanText_(body.qmEmployeeNo, 80) : String(room.qm_employee_no || '');
    const target = action === 'CLEANING_START' ? 'CLEANING' : (qmEmployeeNo ? 'QM_WAITING' : 'COMPLETED');
    if (room.cleaning_status === target) {
      const response = {
        ok: true,
        action,
        requestId,
        idempotent: true,
        alreadyCompleted: action === 'CLEANING_COMPLETE',
        room: roomDto(room),
        version: Number(room.version || 0),
        timing: { totalMs: Date.now() - startedAt }
      };
      await client.query(
        `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
        [requestId, JSON.stringify(response)]
      );
      await client.query('commit');
      return res.json(response);
    }

    if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
      throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
        currentRoom: roomDto(room)
      });
    }

    if (action === 'CLEANING_START' && !['ASSIGNED', 'WAITING', 'REWORK'].includes(room.cleaning_status)) {
      throw httpError(409, 'INVALID_STATE', `현재 ${room.cleaning_status} 상태에서는 청소시작할 수 없습니다.`);
    }
    if (action === 'CLEANING_COMPLETE' && room.cleaning_status !== 'CLEANING') {
      throw httpError(409, 'INVALID_STATE', `현재 ${room.cleaning_status} 상태에서는 청소완료할 수 없습니다.`);
    }

    const before = room.cleaning_status;
    const updated = await client.query(
      `update public.nova_rooms_current
          set cleaning_status=$4,
              version=version+1,
              cleaning_started_at=case when $4='CLEANING' then coalesce(cleaning_started_at,now()) else cleaning_started_at end,
              cleaning_completed_at=case when $4 in ('COMPLETED','QM_WAITING') then now() else cleaning_completed_at end,
              updated_by=$5,
              qm_employee_no=case when $6::boolean then nullif($7,'') else qm_employee_no end,
              updated_at=now()
        where business_date=$1 and site=$2 and room_no=$3
        returning *`,
      [businessDate, site, roomNo, target, user.employee_no, hasQmHint, qmEmployeeNo]
    );
    const nextRoom = updated.rows[0];

    await client.query(
      `insert into public.nova_room_events(
        request_id,business_date,site,room_no,action,before_status,after_status,
        employee_no,room_version,detail
      ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
      [
        requestId, businessDate, site, roomNo, action, before, target, user.employee_no,
        nextRoom.version, JSON.stringify({ source: 'NOVA_REALTIME', role: user.role })
      ]
    );

    const response = {
      ok: true,
      action,
      requestId,
      room: roomDto(nextRoom),
      version: Number(nextRoom.version || 0),
      timing: { totalMs: Date.now() - startedAt }
    };
    await client.query(
      `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
      [requestId, JSON.stringify(response)]
    );
    await client.query('commit');
    res.json(response);
  } catch (e) {
    if (client) {
      try { await client.query('rollback'); } catch {}
    }
    next(e);
  } finally {
    if (client) client.release();
  }
});'''
cloud = cloud[:route_start] + new_route + cloud[route_end:]

# Extend /v1/room-changes so other admin clients receive assignment fields too.
cloud = replace_once(
    cloud,
    "      select request_id,business_date,site,room_no,after_status,room_version,event_time\n        from public.nova_room_events",
    "      select request_id,business_date,site,room_no,action,after_status,room_version,detail,event_time\n        from public.nova_room_events",
    'room-changes select assignment detail'
)
old_changes = """    const changes = rows.map(row => ({
      requestId: String(row.request_id || ''),
      eventTime: row.event_time instanceof Date ? row.event_time.toISOString() : String(row.event_time || ''),
      room: {
        businessDate: row.business_date instanceof Date ? row.business_date.toISOString().slice(0, 10) : String(row.business_date || '').slice(0, 10),
        site: String(row.site || ''),
        roomNo: String(row.room_no || ''),
        cleaningStatus: String(row.after_status || ''),
        version: Number(row.room_version || 0),
        updatedAt: row.event_time instanceof Date ? row.event_time.toISOString() : String(row.event_time || '')
      }
    }));"""
new_changes = """    const changes = rows.map(row => {
      const action = String(row.action || '').trim().toUpperCase();
      const detail = row.detail && typeof row.detail === 'object' ? row.detail : {};
      const room = {
        businessDate: row.business_date instanceof Date ? row.business_date.toISOString().slice(0, 10) : String(row.business_date || '').slice(0, 10),
        site: String(row.site || ''),
        roomNo: String(row.room_no || ''),
        cleaningStatus: String(row.after_status || ''),
        version: Number(row.room_version || 0),
        updatedAt: row.event_time instanceof Date ? row.event_time.toISOString() : String(row.event_time || '')
      };
      if (action === 'ASSIGN_ROOMMAID') {
        room.cleaningType = String(detail.cleaningType || 'NORMAL');
        room.assignmentType = String(detail.assignmentType || 'SOLO');
        room.roommaidEmployeeNo = String(detail.primaryEmployeeNo || '');
        room.secondaryRoommaidEmployeeNo = String(detail.secondaryEmployeeNo || '');
      }
      return {
        requestId: String(row.request_id || ''),
        eventTime: row.event_time instanceof Date ? row.event_time.toISOString() : String(row.event_time || ''),
        room
      };
    });"""
cloud = replace_once(cloud, old_changes, new_changes, 'room-changes assignment mapping')

# Save backups + patched files.
backup(CLIENT, '.backup_v19_before_assignment_realtime')
backup(SYNC, '.backup_v19_before_assignment_realtime')
backup(CLOUD, '.backup_v38_before_assignment_realtime')
CLIENT.write_text(client, encoding='utf-8')
SYNC.write_text(sync, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')

# Guard rails.
subprocess.run(['node', '--check', str(SYNC)], cwd=REPO, check=True)
subprocess.run(['node', '--check', str(CLOUD)], cwd=CLOUD.parent, check=True)
subprocess.run(['git', 'diff', '--check', '--', 'Client.html', 'RealtimeDailySync.js'], cwd=REPO, check=True)

print('PATCH_OK')
print('Apps Script changed: Client.html, RealtimeDailySync.js')
print('Cloud Run changed: ~/nova-realtime/cloud-run/index.js')
print('Realtime added: ASSIGN_ROOMMAID')
print('Preserved: existing UI, optimistic room card rendering, START/COMPLETE flow, Sheets history, Telegram')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js'], cwd=REPO, check=True)
