#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'
SYNC = ROOT / 'RealtimeDailySync.js'
CLOUD = ROOT / 'cloudrun' / 'index.js'


def fail(message):
    print(f'PATCH_ERROR: {message}')
    sys.exit(1)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


for path in (CLIENT, SYNC, CLOUD):
    if not path.exists():
        fail(f'file not found: {path}')

# -----------------------------------------------------------------------------
# Client: restore the missing assignment-reset button and route CLEAR_ASSIGNMENT
# through the existing Realtime room-action endpoint.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')

client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS'].includes(mappedAction)",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)",
    'Client CLEAR_ASSIGNMENT realtime routing'
)

client = replace_once(
    client,
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : '청소완료 처리했습니다.');",
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : mappedAction === 'CLEAR_ASSIGNMENT' ? '배정을 초기화했습니다.' : '청소완료 처리했습니다.');",
    'Client CLEAR_ASSIGNMENT result message'
)

client = replace_once(
    client,
    '            <button class="action-button" type="button" data-room-action="ASSIGN_ROOMMAID">배정</button>\n            <button class="action-button" type="button" data-room-action="CLEANING_START">청소시작</button>',
    '            <button class="action-button" type="button" data-room-action="ASSIGN_ROOMMAID">배정</button>\n            <button class="action-button danger" type="button" data-room-action="CLEAR_ASSIGNMENT">배정 초기화</button>\n            <button class="action-button" type="button" data-room-action="CLEANING_START">청소시작</button>',
    'Client assignment-reset button restore'
)

client = replace_once(
    client,
    "      const resultRoom = Object.assign({}, result.room || {});\n      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {",
    "      const resultRoom = Object.assign({}, result.room || {});\n      if (action === 'CLEAR_ASSIGNMENT') {\n        Object.assign(resultRoom, emptyRoomAssignmentPatch_(), { cleaningStatus: 'WAITING' });\n      }\n      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {",
    'Client CLEAR_ASSIGNMENT confirmed-room normalization'
)

# -----------------------------------------------------------------------------
# RealtimeDailySync: mirror CLEAR_ASSIGNMENT into the exact existing Sheet fields
# and unified history. No existing business-rule function is removed.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
sync_anchor = "      if (action === 'UPDATE_OPERATION_FLAGS') {"
if sync.count(sync_anchor) != 1:
    fail(f'RealtimeDailySync UPDATE_OPERATION_FLAGS anchor: expected 1 match, found {sync.count(sync_anchor)}')

clear_sync_branch = r'''      if (action === 'CLEAR_ASSIGNMENT') {
        const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
        const previousCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
        const previousCleaningType = String(rowInfo.data['정비유형'] || '').trim().toUpperCase();
        const previousAssignmentType = String(rowInfo.data['배정유형'] || '').trim().toUpperCase();
        const previousPrimaryEmployeeNo = String(rowInfo.data['룸메이드사번'] || '').trim();
        const previousSecondaryEmployeeNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
        const previousQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
        const previousOperationalStatus = normalizeIndicatorRoomOperationalStatus_(
          rowInfo.data[indicatorRoomOperationalStatusHeader_()]
        );

        const updates = {
          '정비유형': '',
          '배정유형': '',
          '룸메이드사번': '',
          '보조룸메이드사번': '',
          'QM사번': '',
          '청소상태': 'WAITING',
          '수정일시': nowText_(),
          '마지막변경버전': version
        };
        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.CLEANING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'CLEAR_ASSIGNMENT',
          detail: {
            requestId,
            realtime: true,
            action: 'CLEAR_ASSIGNMENT',
            previousRoomStatus,
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            previousCleaningStatus,
            cleaningStatus: 'WAITING',
            previousCleaningType,
            cleaningType: '',
            previousAssignmentType,
            assignmentType: '',
            previousPrimaryEmployeeNo,
            previousSecondaryEmployeeNo,
            previousQmEmployeeNo,
            primaryEmployeeNo: '',
            secondaryEmployeeNo: '',
            qmEmployeeNo: '',
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            previousOperationalStatus,
            operationalStatus: previousOperationalStatus,
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

'''
sync = sync.replace(sync_anchor, clear_sync_branch + sync_anchor, 1)

# -----------------------------------------------------------------------------
# Cloud Run: add CLEAR_ASSIGNMENT to the existing room-action route.
# PostgreSQL keeps NORMAL/SOLO as harmless defaults while all assignee fields are
# cleared; the response/event explicitly expose cleared assignment values.
# -----------------------------------------------------------------------------
cloud = CLOUD.read_text(encoding='utf-8')

cloud = replace_once(
    cloud,
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS'].includes(action)",
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(action)",
    'Cloud Run allowed CLEAR_ASSIGNMENT action'
)

changes_anchor = "          if (action === 'UPDATE_OPERATION_FLAGS') {"
if cloud.count(changes_anchor) != 1:
    fail(f'Cloud Run room-changes UPDATE_OPERATION_FLAGS anchor: expected 1 match, found {cloud.count(changes_anchor)}')
changes_insert = r'''          if (action === 'CLEAR_ASSIGNMENT') {
            delete room.cleaningStatus;
            room.cleaningStatus = 'WAITING';
            room.cleaningType = '';
            room.assignmentType = '';
            room.roommaidEmployeeNo = '';
            room.secondaryRoommaidEmployeeNo = '';
            room.qmEmployeeNo = '';
          }
'''
cloud = cloud.replace(changes_anchor, changes_insert + changes_anchor, 1)

route_start_marker = "app.post(\n  '/v1/rooms/:roomNo/action',"
route_end_marker = "\napp.post(\n  '/v1/houseman-orders',"
route_start = cloud.find(route_start_marker)
if route_start < 0:
    fail('Cloud Run room action route start not found')
route_end = cloud.find(route_end_marker, route_start)
if route_end < 0:
    fail('Cloud Run room action route end not found')
route_segment = cloud[route_start:route_end]
route_anchor = "      if (action === 'UPDATE_OPERATION_FLAGS') {"
if route_segment.count(route_anchor) != 1:
    fail(f'Cloud Run UPDATE_OPERATION_FLAGS route anchor inside room-action route: expected 1 match, found {route_segment.count(route_anchor)}')

clear_route_branch = r'''      if (action === 'CLEAR_ASSIGNMENT') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '객실 배정 초기화 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const alreadyClear = String(room.cleaning_status || '').toUpperCase() === 'WAITING'
          && !String(room.roommaid_employee_no || '')
          && !String(room.secondary_roommaid_employee_no || '')
          && !String(room.qm_employee_no || '');
        if (alreadyClear) {
          const responseRoom = {
            ...roomDto(room),
            cleaningStatus: 'WAITING',
            cleaningType: '',
            assignmentType: '',
            roommaidEmployeeNo: '',
            secondaryRoommaidEmployeeNo: '',
            qmEmployeeNo: ''
          };
          const response = {
            ok: true,
            action,
            requestId,
            idempotent: true,
            room: responseRoom,
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

        const previousCleaningStatus = String(room.cleaning_status || '');
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          previousCleaningStatus,
          previousCleaningType: String(room.cleaning_type || ''),
          previousAssignmentType: String(room.assignment_type || ''),
          previousPrimaryEmployeeNo: String(room.roommaid_employee_no || ''),
          previousSecondaryEmployeeNo: String(room.secondary_roommaid_employee_no || ''),
          previousQmEmployeeNo: String(room.qm_employee_no || ''),
          cleaningStatus: 'WAITING',
          cleaningType: '',
          assignmentType: '',
          primaryEmployeeNo: '',
          secondaryEmployeeNo: '',
          qmEmployeeNo: ''
        };

        const updated = await client.query(
          `update public.nova_rooms_current
              set cleaning_status='WAITING',
                  cleaning_type='NORMAL',
                  assignment_type='SOLO',
                  roommaid_employee_no=null,
                  secondary_roommaid_employee_no=null,
                  qm_employee_no=null,
                  version=version+1,
                  updated_by=$4,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [businessDate, site, roomNo, user.employee_no]
        );
        const nextRoom = updated.rows[0];

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
            previousCleaningStatus,
            'WAITING',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const responseRoom = {
          ...roomDto(nextRoom),
          cleaningStatus: 'WAITING',
          cleaningType: '',
          assignmentType: '',
          roommaidEmployeeNo: '',
          secondaryRoommaidEmployeeNo: '',
          qmEmployeeNo: ''
        };
        const response = {
          ok: true,
          action,
          requestId,
          room: responseRoom,
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
route_segment = route_segment.replace(route_anchor, clear_route_branch + route_anchor, 1)
cloud = cloud[:route_start] + route_segment + cloud[route_end:]

# Backups once.
for path in (CLIENT, SYNC, CLOUD):
    backup = path.with_name(path.name + '.backup_before_v25_clear_assignment')
    if not backup.exists():
        backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')

CLIENT.write_text(client, encoding='utf-8')
SYNC.write_text(sync, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')

# Validate before any deployment.
subprocess.run(['node', '--check', str(CLOUD)], cwd=ROOT, check=True)
client_text = CLIENT.read_text(encoding='utf-8')
start = client_text.find('<script>')
end = client_text.rfind('</script>')
if start < 0 or end <= start:
    fail('Client embedded script not found')
tmp = ROOT / '.tmp_client_v25.js'
tmp.write_text(client_text[start + len('<script>'):end], encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(tmp)], cwd=ROOT, check=True)
    subprocess.run(['git', 'diff', '--check', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)
finally:
    if tmp.exists():
        tmp.unlink()

print('PATCH_OK')
print('Repository only; production Cloud Run NOT changed yet')
print('Changed: Client.html, RealtimeDailySync.js, cloudrun/index.js')
print('Restored: 객실 작업 > 배정 초기화 button')
print('Added: CLEAR_ASSIGNMENT Realtime primary save + existing Sheet/history mirror')
print('Preserved: existing UI/functions/permissions and all other room-action paths')
print('Syntax: PASS')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)
