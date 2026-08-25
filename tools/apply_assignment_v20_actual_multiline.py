#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'
SYNC = ROOT / 'RealtimeDailySync.js'
CLOUD_SNAPSHOT = ROOT / 'cloudrun' / 'index.js'


def fail(msg):
    print(f'PATCH_ERROR: {msg}')
    sys.exit(1)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


def write_backup(path, suffix):
    backup = path.with_name(path.name + suffix)
    if not backup.exists():
        backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')

for path in (CLIENT, SYNC, CLOUD_SNAPSHOT):
    if not path.exists():
        fail(f'file not found: {path}')

# -----------------------------------------------------------------------------
# Client.html
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')
client_original = client

client = replace_once(
    client,
    "    'cleaningStatus', 'version', 'updatedAt'",
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'version', 'updatedAt'",
    'Realtime owned room fields'
)

client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE'].includes(mappedAction);",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID'].includes(mappedAction);",
    'Realtime room action list'
)

client = replace_once(
    client,
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : '청소완료 처리했습니다.');",
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : '청소완료 처리했습니다.');",
    'Realtime room action result message'
)

client = replace_once(
    client,
    "      if (!['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE'].includes(code)) throw error;",
    "      if (!['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE', 'ROOMMAID_NOT_AVAILABLE'].includes(code)) throw error;",
    'Realtime JIT retry codes'
)

old_room_changes = r'''  async function novaRealtimeRoomChangesFetch_(payload, attempt = 0) {
    const form = new URLSearchParams();
    Object.entries(payload || {}).forEach(([key, value]) => {
      form.set(key, value == null ? '' : String(value));
    });
    form.set('token', String(state.token || ''));

    const response = await fetch(`${novaRealtime_.apiBase}/v1/room-changes`, {
      method: 'POST',
      body: form
    }).catch(error => {
      if (attempt < 2) return null;
      throw error;
    });

    if (!response) {
      await novaRealtimeSleep_([160, 420, 800][attempt] || 800);
      return novaRealtimeRoomChangesFetch_(payload, attempt + 1);
    }

    let data = {};
    try { data = await response.json(); } catch (ignore) {}
    if (response.ok && data?.ok) return data;

    const retryable = response.status === 429 || response.status >= 500;
    if (retryable && attempt < 2) {
      await novaRealtimeSleep_([160, 420, 800][attempt] || 800);
      return novaRealtimeRoomChangesFetch_(payload, attempt + 1);
    }

    const error = new Error(data?.message || data?.error || `Realtime 변경조회 실패 (${response.status})`);
    error.status = response.status;
    error.code = data?.code || '';
    error.data = data;
    throw error;
  }
'''
new_room_changes = r'''  async function novaRealtimeRoomChangesFetch_(payload, attempt = 0) {
    const query = new URLSearchParams();
    Object.entries(payload || {}).forEach(([key, value]) => {
      query.set(key, value == null ? '' : String(value));
    });

    const response = await fetch(`${novaRealtime_.apiBase}/v1/room-changes?${query.toString()}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${state.token}`
      }
    }).catch(error => {
      if (attempt < 2) return null;
      throw error;
    });

    if (!response) {
      await novaRealtimeSleep_([160, 420, 800][attempt] || 800);
      return novaRealtimeRoomChangesFetch_(payload, attempt + 1);
    }

    let data = {};
    try { data = await response.json(); } catch (ignore) {}
    if (response.ok && data?.ok) return data;

    const retryable = response.status === 429 || response.status >= 500;
    if (retryable && attempt < 2) {
      await novaRealtimeSleep_([160, 420, 800][attempt] || 800);
      return novaRealtimeRoomChangesFetch_(payload, attempt + 1);
    }

    const error = new Error(data?.message || data?.error || `Realtime 변경조회 실패 (${response.status})`);
    error.status = response.status;
    error.code = data?.code || '';
    error.data = data;
    throw error;
  }
'''
client = replace_once(client, old_room_changes, new_room_changes, 'room-changes GET contract')

old_merge_tail = r'''    NOVA_REALTIME_ROOM_FIELDS_.forEach(key => {
      if (Object.prototype.hasOwnProperty.call(realtimeRoom, key)) merged[key] = realtimeRoom[key];
    });
    if (realtimeRoom.building) merged.building = realtimeRoom.building;
    return merged;
'''
new_merge_tail = r'''    NOVA_REALTIME_ROOM_FIELDS_.forEach(key => {
      if (Object.prototype.hasOwnProperty.call(realtimeRoom, key)) merged[key] = realtimeRoom[key];
    });
    if (realtimeRoom.building) merged.building = realtimeRoom.building;

    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'roommaidEmployeeNo')
        || Object.prototype.hasOwnProperty.call(realtimeRoom, 'secondaryRoommaidEmployeeNo')) {
      const staff = state.indicator.data?.staff?.roommaids || [];
      const primaryNo = String(merged.roommaidEmployeeNo || '').trim();
      const secondaryNo = String(merged.secondaryRoommaidEmployeeNo || '').trim();
      const primary = staff.find(user => String(user.employeeNo || '').trim() === primaryNo);
      const secondary = staff.find(user => String(user.employeeNo || '').trim() === secondaryNo);
      merged.roommaidName = primaryNo ? String(primary?.name || primaryNo) : '';
      merged.secondaryRoommaidName = secondaryNo ? String(secondary?.name || secondaryNo) : '';
    }
    return merged;
'''
client = replace_once(client, old_merge_tail, new_merge_tail, 'Realtime assignment name merge')

# -----------------------------------------------------------------------------
# RealtimeDailySync.js
# Keep START/COMPLETE path untouched and add a dedicated ASSIGN_ROOMMAID branch.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
sync_original = sync
sync = replace_once(
    sync,
    "  const qmNotifications = [];\n",
    "  const qmNotifications = [];\n  const assignmentNotifications = [];\n",
    'assignment notifications array'
)

assignment_branch_anchor = """      const eventRoomNo = String(event.roomNo || '').trim();\n\n      roomUpdates.push({"""
assignment_branch = """      const eventRoomNo = String(event.roomNo || '').trim();\n\n      if (action === 'ASSIGN_ROOMMAID') {\n        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};\n        const assignedCleaningType = String(eventDetail.cleaningType || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase();\n        const assignedAssignmentType = String(eventDetail.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase();\n        const assignedPrimaryNo = String(eventDetail.primaryEmployeeNo || '').trim();\n        const assignedSecondaryNo = String(eventDetail.secondaryEmployeeNo || '').trim();\n        if (!assignedPrimaryNo) throw new Error(`DB 배정 이벤트에 주담당 사번이 없습니다. (${eventSite} ${eventRoomNo}호)`);\n\n        roomUpdates.push({\n          rowNumber: rowInfo.rowNumber,\n          cleaningStatus: 'ASSIGNED',\n          cleaningType: assignedCleaningType,\n          assignmentType: assignedAssignmentType,\n          roommaidEmployeeNo: assignedPrimaryNo,\n          secondaryRoommaidEmployeeNo: assignedSecondaryNo,\n          version,\n          updatedAt: nowText_()\n        });\n\n        rowInfo.data['청소상태'] = 'ASSIGNED';\n        rowInfo.data['정비유형'] = assignedCleaningType;\n        rowInfo.data['배정유형'] = assignedAssignmentType;\n        rowInfo.data['룸메이드사번'] = assignedPrimaryNo;\n        rowInfo.data['보조룸메이드사번'] = assignedSecondaryNo;\n\n        historyPayloads.push({\n          recordType: NOVA.RECORD_TYPES.CLEANING,\n          businessDate: eventBusinessDate,\n          site: eventSite,\n          roomNo: eventRoomNo,\n          targetEmployeeNo: assignedPrimaryNo,\n          status: 'ASSIGN_ROOMMAID',\n          detail: {\n            requestId,\n            realtime: true,\n            action: 'ASSIGN_ROOMMAID',\n            role: String(eventDetail.role || 'ORDER').trim().toUpperCase(),\n            previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),\n            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),\n            cleaningStatus: 'ASSIGNED',\n            cleaningType: assignedCleaningType,\n            assignmentType: assignedAssignmentType,\n            primaryEmployeeNo: assignedPrimaryNo,\n            secondaryEmployeeNo: assignedSecondaryNo,\n            dbRoomVersion: Number(event.roomVersion || 0),\n            dbEventTime: String(event.eventTime || '')\n          },\n          registeredBy: employeeNo,\n          version\n        });\n\n        const telegramBase = {\n          businessDate: eventBusinessDate,\n          site: eventSite,\n          roomNo: eventRoomNo,\n          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),\n          cleaningType: assignedCleaningType,\n          cleaningStatus: 'ASSIGNED',\n          assignmentType: assignedAssignmentType,\n          preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',\n          vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',\n          importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',\n          registeredBy: employeeNo,\n          version\n        };\n        if (usersByEmployeeNo[assignedPrimaryNo]) {\n          assignmentNotifications.push(Object.assign({}, telegramBase, {\n            targetUser: usersByEmployeeNo[assignedPrimaryNo], assignmentRole: 'PRIMARY'\n          }));\n        }\n        if (assignedSecondaryNo && usersByEmployeeNo[assignedSecondaryNo]) {\n          assignmentNotifications.push(Object.assign({}, telegramBase, {\n            targetUser: usersByEmployeeNo[assignedSecondaryNo], assignmentRole: 'SECONDARY'\n          }));\n        }\n\n        alreadyApplied.add(requestId);\n        mirrored += 1;\n        continue;\n      }\n\n      roomUpdates.push({"""
sync = replace_once(sync, assignment_branch_anchor, assignment_branch, 'assignment mirror branch')

sync = replace_once(
    sync,
    "    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));",
    "    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));\n    assignmentNotifications.forEach(payload => queueCleaningAssignmentTelegram_(payload));",
    'assignment Telegram dispatch'
)

batch_start = sync.find("function novaRealtimeFinalBatchUpdateCurrentRows_(sheet, updates) {")
batch_end = sync.find("function novaRealtimeFinalAppendHistoryBatch_(payloads) {", batch_start)
if batch_start < 0 or batch_end < 0:
    fail('Realtime batch update function markers not found')
new_batch = """function novaRealtimeFinalBatchUpdateCurrentRows_(sheet, updates) { // (Realtime 객실상태·배정·버전 일괄기록)\n  if (!updates.length) return;\n  const headerMap = getHeaderMap_(sheet);\n  const columns = {\n    cleaningStatus: Number(headerMap['청소상태'] || 0),\n    cleaningType: Number(headerMap['정비유형'] || 0),\n    assignmentType: Number(headerMap['배정유형'] || 0),\n    roommaidEmployeeNo: Number(headerMap['룸메이드사번'] || 0),\n    secondaryRoommaidEmployeeNo: Number(headerMap['보조룸메이드사번'] || 0),\n    version: Number(headerMap['마지막변경버전'] || 0),\n    updatedAt: Number(headerMap['수정일시'] || 0)\n  };\n  if (Object.values(columns).some(value => !value)) {\n    throw new Error('현재객실현황 Realtime 반영 열을 찾을 수 없습니다.');\n  }\n\n  const latestByRow = new Map();\n  updates.forEach(item => latestByRow.set(Number(item.rowNumber), item));\n  const rows = Array.from(latestByRow.keys()).filter(row => row >= 2).sort((a, b) => a - b);\n  if (!rows.length) return;\n  const firstRow = rows[0];\n  const lastRow = rows[rows.length - 1];\n  const count = lastRow - firstRow + 1;\n\n  const valuesByKey = {};\n  Object.entries(columns).forEach(([key, column]) => {\n    valuesByKey[key] = sheet.getRange(firstRow, column, count, 1).getValues();\n  });\n  rows.forEach(rowNumber => {\n    const item = latestByRow.get(rowNumber);\n    const offset = rowNumber - firstRow;\n    Object.keys(columns).forEach(key => {\n      if (Object.prototype.hasOwnProperty.call(item, key)) valuesByKey[key][offset][0] = item[key];\n    });\n  });\n  Object.entries(columns).forEach(([key, column]) => {\n    sheet.getRange(firstRow, column, count, 1).setValues(valuesByKey[key]);\n  });\n}\n\n"""
sync = sync[:batch_start] + new_batch + sync[batch_end:]

# -----------------------------------------------------------------------------
# cloudrun/index.js snapshot copied from the actual production source.
# Use regex for multiline Express formatting; never rely on one-line markers.
# -----------------------------------------------------------------------------
cloud = CLOUD_SNAPSHOT.read_text(encoding='utf-8')
cloud_original = cloud

route_re = re.compile(
    r"app\.post\(\s*['\"]\/v1\/rooms\/:roomNo\/action['\"]\s*,\s*async\s*\(req,\s*res,\s*next\)\s*=>\s*\{",
    re.M
)
house_re = re.compile(r"app\.post\(\s*['\"]\/v1\/houseman-orders['\"]", re.M)
route_matches = list(route_re.finditer(cloud))
house_matches = list(house_re.finditer(cloud))
if len(route_matches) != 1 or len(house_matches) != 1:
    fail(f'production Cloud Run route discovery failed: room={len(route_matches)}, houseman={len(house_matches)}')
route_start = route_matches[0].start()
route_end = house_matches[0].start()
if route_end <= route_start:
    fail('Cloud Run route order is invalid')
route = cloud[route_start:route_end]

allowed_re = re.compile(
    r"!\[\s*['\"]CLEANING_START['\"]\s*,\s*['\"]CLEANING_COMPLETE['\"]\s*\]\.includes\(action\)",
    re.M
)
if len(allowed_re.findall(route)) != 1:
    fail(f'Cloud Run allowed-action marker expected 1, found {len(allowed_re.findall(route))}')
route = allowed_re.sub(
    "!['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID'].includes(action)",
    route,
    count=1
)

can_clean_re = re.compile(r"\n\s*if\s*\(\s*!canCleanRoom\(\s*user\s*,\s*room\s*\)\s*\)\s*\{", re.M)
can_match = can_clean_re.search(route)
if not can_match:
    fail('Cloud Run canCleanRoom marker not found')

assignment_branch = r'''

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
        const rawSecondaryEmployeeNo = cleanText_(body.secondaryEmployeeNo, 80);
        const assignmentType = cleanText_(body.assignmentType || 'SOLO', 40).toUpperCase();
        const cleaningType = cleanText_(body.cleaningType || 'NORMAL', 40).toUpperCase();
        const pairAssignment = ['PAIR', 'PAIR_TRAINING'].includes(assignmentType);
        const secondaryEmployeeNo = pairAssignment ? rawSecondaryEmployeeNo : '';

        if (!primaryEmployeeNo) {
          throw httpError(400, 'ROOMMAID_REQUIRED', '주담당 룸메이드를 선택하세요.');
        }
        if (!['SOLO', 'PAIR', 'PAIR_TRAINING'].includes(assignmentType)) {
          throw httpError(400, 'INVALID_ASSIGNMENT_TYPE', '지원하지 않는 룸메이드 배정유형입니다.');
        }
        if (pairAssignment && !secondaryEmployeeNo) {
          throw httpError(400, 'SECONDARY_ROOMMAID_REQUIRED', '보조 룸메이드를 선택하세요.');
        }
        if (secondaryEmployeeNo && primaryEmployeeNo === secondaryEmployeeNo) {
          throw httpError(400, 'DUPLICATE_ROOMMAID', '주담당과 보조 룸메이드는 서로 달라야 합니다.');
        }

        const employeeNos = pairAssignment
          ? [primaryEmployeeNo, secondaryEmployeeNo]
          : [primaryEmployeeNo];
        const staffResult = await client.query(
          `select employee_no,name,role,enabled
             from public.nova_users
            where employee_no = any($1::text[])`,
          [employeeNos]
        );
        const staffByNo = Object.fromEntries(
          staffResult.rows.map(item => [String(item.employee_no || ''), item])
        );
        const primaryUser = staffByNo[primaryEmployeeNo] || null;
        const secondaryUser = secondaryEmployeeNo ? (staffByNo[secondaryEmployeeNo] || null) : null;

        if (!primaryUser || !primaryUser.enabled || String(primaryUser.role || '').toUpperCase() !== 'ROOMMAID') {
          throw httpError(400, 'ROOMMAID_NOT_AVAILABLE', '주담당 룸메이드 정보를 확인할 수 없습니다.');
        }
        if (pairAssignment && (!secondaryUser || !secondaryUser.enabled || String(secondaryUser.role || '').toUpperCase() !== 'ROOMMAID')) {
          throw httpError(400, 'ROOMMAID_NOT_AVAILABLE', '보조 룸메이드 정보를 확인할 수 없습니다.');
        }

        const sameAssignment = String(room.cleaning_status || '').toUpperCase() === 'ASSIGNED'
          && String(room.cleaning_type || 'NORMAL').toUpperCase() === cleaningType
          && String(room.assignment_type || 'SOLO').toUpperCase() === assignmentType
          && String(room.roommaid_employee_no || '') === primaryEmployeeNo
          && String(room.secondary_roommaid_employee_no || '') === secondaryEmployeeNo;

        if (sameAssignment) {
          const response = {
            ok: true,
            action,
            requestId,
            idempotent: true,
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
          [
            businessDate,
            site,
            roomNo,
            cleaningType,
            assignmentType,
            primaryEmployeeNo,
            secondaryEmployeeNo,
            user.employee_no
          ]
        );
        const nextRoom = updated.rows[0];

        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          cleaningType,
          assignmentType,
          primaryEmployeeNo,
          primaryName: String(primaryUser.name || ''),
          secondaryEmployeeNo,
          secondaryName: secondaryUser ? String(secondaryUser.name || '') : ''
        };

        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            'ASSIGNED',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
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
        return res.json(response);
      }
'''
route = route[:can_match.start()] + assignment_branch + route[can_match.start():]
cloud = cloud[:route_start] + route + cloud[route_end:]

# -----------------------------------------------------------------------------
# Save only repository files. Live Cloud Run is intentionally untouched here.
# -----------------------------------------------------------------------------
write_backup(CLIENT, '.backup_v19_before_assignment_realtime')
write_backup(SYNC, '.backup_v19_before_assignment_realtime')
write_backup(CLOUD_SNAPSHOT, '.backup_before_assignment_realtime')
CLIENT.write_text(client, encoding='utf-8')
SYNC.write_text(sync, encoding='utf-8')
CLOUD_SNAPSHOT.write_text(cloud, encoding='utf-8')

# Syntax / diff guards.
subprocess.run(['node', '--check', str(SYNC)], cwd=ROOT, check=True)
subprocess.run(['node', '--check', str(CLOUD_SNAPSHOT)], cwd=ROOT, check=True)
subprocess.run(['git', 'diff', '--check', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)

# Verify the intended route exists exactly once after patching.
patched_cloud = CLOUD_SNAPSHOT.read_text(encoding='utf-8')
if patched_cloud.count("ASSIGN_ROOMMAID") < 1:
    fail('ASSIGN_ROOMMAID was not added to Cloud Run snapshot')

print('PATCH_OK')
print('Repository only; production Cloud Run NOT changed yet')
print('Changed: Client.html, RealtimeDailySync.js, cloudrun/index.js')
print('Added: ASSIGN_ROOMMAID Realtime + room-changes GET fix + assignment mirror')
print('Syntax: PASS')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)
