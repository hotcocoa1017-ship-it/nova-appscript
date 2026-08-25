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

client = CLIENT.read_text(encoding='utf-8')
sync = SYNC.read_text(encoding='utf-8')
cloud = CLOUD.read_text(encoding='utf-8')
client_original = client
sync_original = sync
cloud_original = cloud

# -----------------------------------------------------------------------------
# Client: QM_ASSIGN uses the existing Realtime room-action path.
# -----------------------------------------------------------------------------
client = replace_once(
    client,
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'version', 'updatedAt'",
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'version', 'updatedAt'",
    'Client realtime room fields'
)

roommaid_merge = """    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'roommaidEmployeeNo')
        || Object.prototype.hasOwnProperty.call(realtimeRoom, 'secondaryRoommaidEmployeeNo')) {
      const staff = state.indicator.data?.staff?.roommaids || [];
      const primaryNo = String(merged.roommaidEmployeeNo || '').trim();
      const secondaryNo = String(merged.secondaryRoommaidEmployeeNo || '').trim();
      const primary = staff.find(user => String(user.employeeNo || '').trim() === primaryNo);
      const secondary = staff.find(user => String(user.employeeNo || '').trim() === secondaryNo);
      merged.roommaidName = primaryNo ? String(primary?.name || primaryNo) : '';
      merged.secondaryRoommaidName = secondaryNo ? String(secondary?.name || secondaryNo) : '';
    }
    return merged;"""
roommaid_qm_merge = """    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'roommaidEmployeeNo')
        || Object.prototype.hasOwnProperty.call(realtimeRoom, 'secondaryRoommaidEmployeeNo')) {
      const staff = state.indicator.data?.staff?.roommaids || [];
      const primaryNo = String(merged.roommaidEmployeeNo || '').trim();
      const secondaryNo = String(merged.secondaryRoommaidEmployeeNo || '').trim();
      const primary = staff.find(user => String(user.employeeNo || '').trim() === primaryNo);
      const secondary = staff.find(user => String(user.employeeNo || '').trim() === secondaryNo);
      merged.roommaidName = primaryNo ? String(primary?.name || primaryNo) : '';
      merged.secondaryRoommaidName = secondaryNo ? String(secondary?.name || secondaryNo) : '';
    }
    if (Object.prototype.hasOwnProperty.call(realtimeRoom, 'qmEmployeeNo')) {
      const staff = state.indicator.data?.staff?.qms || [];
      const qmNo = String(merged.qmEmployeeNo || '').trim();
      const qm = staff.find(user => String(user.employeeNo || '').trim() === qmNo);
      merged.qmName = qmNo ? String(qm?.name || qmNo) : '';
    }
    return merged;"""
client = replace_once(client, roommaid_merge, roommaid_qm_merge, 'Client QM name merge')

client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID'].includes(mappedAction);",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN'].includes(mappedAction);",
    'Client realtime action list'
)
client = replace_once(
    client,
    "      if (!['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE', 'ROOMMAID_NOT_AVAILABLE'].includes(code)) throw error;",
    "      if (!['ROOM_NOT_FOUND', 'FORBIDDEN', 'INVALID_STATE', 'ROOMMAID_NOT_AVAILABLE', 'QM_NOT_AVAILABLE'].includes(code)) throw error;",
    'Client JIT retry codes'
)
client = replace_once(
    client,
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : '청소완료 처리했습니다.');",
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : '청소완료 처리했습니다.');",
    'Client QM success message'
)

# -----------------------------------------------------------------------------
# RealtimeDailySync: mirror QM_ASSIGN into CURRENT / history / Telegram.
# -----------------------------------------------------------------------------
sync = replace_once(
    sync,
    "  const qmNotifications = [];\n  const assignmentNotifications = [];",
    "  const qmNotifications = [];\n  const assignmentNotifications = [];\n  const qmAssignmentNotifications = [];",
    'QM assignment notification array'
)

assign_end = """        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      roomUpdates.push({"""
qm_branch = """        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      if (action === 'QM_ASSIGN') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const assignedQmNo = String(eventDetail.qmEmployeeNo || '').trim();
        if (!assignedQmNo) throw new Error(`DB QM 배정 이벤트에 QM 사번이 없습니다. (${eventSite} ${eventRoomNo}호)`);

        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: 'QM_WAITING',
          qmEmployeeNo: assignedQmNo,
          version,
          updatedAt: nowText_()
        });
        rowInfo.data['청소상태'] = 'QM_WAITING';
        rowInfo.data['QM사번'] = assignedQmNo;

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: assignedQmNo,
          status: 'QM_ASSIGN',
          detail: {
            requestId,
            realtime: true,
            action: 'QM_ASSIGN',
            role: String(eventDetail.role || 'ORDER').trim().toUpperCase(),
            previousRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            cleaningStatus: 'QM_WAITING',
            cleaningType,
            assignmentType,
            primaryEmployeeNo: roommaidNo,
            secondaryEmployeeNo: secondaryRoommaidNo,
            qmEmployeeNo: assignedQmNo,
            dbRoomVersion: Number(event.roomVersion || 0),
            dbEventTime: String(event.eventTime || '')
          },
          registeredBy: employeeNo,
          version
        });

        if (usersByEmployeeNo[assignedQmNo]) {
          qmAssignmentNotifications.push({
            businessDate: eventBusinessDate,
            site: eventSite,
            roomNo: eventRoomNo,
            targetUser: usersByEmployeeNo[assignedQmNo],
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            registeredBy: employeeNo,
            version
          });
        }

        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

      roomUpdates.push({"""
sync = replace_once(sync, assign_end, qm_branch, 'QM event mirror branch')

sync = replace_once(
    sync,
    "    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));\n    assignmentNotifications.forEach(payload => queueCleaningAssignmentTelegram_(payload));",
    "    qmNotifications.forEach(payload => queueQmReadyTelegram_(payload));\n    assignmentNotifications.forEach(payload => queueCleaningAssignmentTelegram_(payload));\n    qmAssignmentNotifications.forEach(payload => queueQmAssignmentTelegram_(payload));",
    'QM assignment Telegram dispatch'
)

sync = replace_once(
    sync,
    "    secondaryRoommaidEmployeeNo: Number(headerMap['보조룸메이드사번'] || 0),\n    version: Number(headerMap['마지막변경버전'] || 0),",
    "    secondaryRoommaidEmployeeNo: Number(headerMap['보조룸메이드사번'] || 0),\n    qmEmployeeNo: Number(headerMap['QM사번'] || 0),\n    version: Number(headerMap['마지막변경버전'] || 0),",
    'QM current sheet column'
)

# -----------------------------------------------------------------------------
# Cloud Run: add QM_ASSIGN to current room action endpoint.
# -----------------------------------------------------------------------------
route_start = cloud.find("app.post(\n  '/v1/rooms/:roomNo/action',")
route_end = cloud.find("app.post(\n  '/v1/houseman-orders',", route_start)
if route_start < 0 or route_end < 0:
    fail('Cloud Run room action route boundaries not found')
route = cloud[route_start:route_end]
route = replace_once(
    route,
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID'].includes(action)",
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN'].includes(action)",
    'Cloud Run action list'
)

can_clean_anchor = """

      if (
        !canCleanRoom(
          user,
          room
        )
      ) {"""
qm_route = """

      if (action === 'QM_ASSIGN') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', 'QM 배정 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const qmEmployeeNo = cleanText_(body.employeeNo, 80);
        if (!qmEmployeeNo) {
          throw httpError(400, 'QM_REQUIRED', '배정할 QM을 선택하세요.');
        }

        const qmResult = await client.query(
          `select employee_no,name,role,enabled
             from public.nova_users
            where employee_no=$1`,
          [qmEmployeeNo]
        );
        const qmUser = qmResult.rows[0] || null;
        if (!qmUser || !qmUser.enabled || String(qmUser.role || '').toUpperCase() !== 'QM') {
          throw httpError(400, 'QM_NOT_AVAILABLE', '배정할 QM 정보를 확인할 수 없습니다.');
        }

        const sameAssignment = String(room.cleaning_status || '').toUpperCase() === 'QM_WAITING'
          && String(room.qm_employee_no || '') === qmEmployeeNo;
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
              set cleaning_status='QM_WAITING',
                  qm_employee_no=$4,
                  version=version+1,
                  updated_by=$5,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [businessDate, site, roomNo, qmEmployeeNo, user.employee_no]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          qmEmployeeNo,
          qmName: String(qmUser.name || '')
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
            'QM_WAITING',
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
""" + can_clean_anchor
route = replace_once(route, can_clean_anchor, qm_route, 'Cloud Run QM branch')
cloud = cloud[:route_start] + route + cloud[route_end:]

# -----------------------------------------------------------------------------
# Cloud Run /v1/room-changes: include assignment/QM detail in fallback polling.
# This also completes the v20 roommaid-assignment fallback path.
# -----------------------------------------------------------------------------
changes_start = cloud.find("app.get(\n  '/v1/room-changes',")
changes_end = cloud.find("app.post(\n  '/v1/rooms/:roomNo/action',", changes_start)
if changes_start < 0 or changes_end < 0:
    fail('Cloud Run room-changes boundaries not found')
changes_route = cloud[changes_start:changes_end]
changes_route = replace_once(
    changes_route,
    """          room_no,
          after_status,
          room_version,
          event_time""",
    """          room_no,
          action,
          after_status,
          room_version,
          detail,
          event_time""",
    'room-changes select detail'
)

old_map_start = changes_route.find("      const changes =\n        rows.map(row => ({")
old_map_end = changes_route.find("\n\n      const hasMore =", old_map_start)
if old_map_start < 0 or old_map_end < 0:
    fail('room-changes mapper boundaries not found')
new_map = """      const changes =
        rows.map(row => {
          const action = String(row.action || '').trim().toUpperCase();
          const detail = row.detail && typeof row.detail === 'object' ? row.detail : {};
          const room = {
            businessDate:
              row.business_date instanceof Date
                ? row.business_date.toISOString().slice(0, 10)
                : String(row.business_date || '').slice(0, 10),
            site: String(row.site || ''),
            roomNo: String(row.room_no || ''),
            cleaningStatus: String(row.after_status || ''),
            version: Number(row.room_version || 0),
            updatedAt:
              row.event_time instanceof Date
                ? row.event_time.toISOString()
                : String(row.event_time || '')
          };
          if (action === 'ASSIGN_ROOMMAID') {
            room.cleaningType = String(detail.cleaningType || 'NORMAL');
            room.assignmentType = String(detail.assignmentType || 'SOLO');
            room.roommaidEmployeeNo = String(detail.primaryEmployeeNo || '');
            room.secondaryRoommaidEmployeeNo = String(detail.secondaryEmployeeNo || '');
          }
          if (action === 'QM_ASSIGN') {
            room.qmEmployeeNo = String(detail.qmEmployeeNo || '');
          }
          return {
            requestId: String(row.request_id || ''),
            eventTime:
              row.event_time instanceof Date
                ? row.event_time.toISOString()
                : String(row.event_time || ''),
            room
          };
        });"""
changes_route = changes_route[:old_map_start] + new_map + changes_route[old_map_end:]
cloud = cloud[:changes_start] + changes_route + cloud[changes_end:]

# Save repository-only changes. Production Cloud Run is copied/deployed only after review.
CLIENT.write_text(client, encoding='utf-8')
SYNC.write_text(sync, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')

# Guard rails.
subprocess.run(['node', '--check', str(SYNC)], cwd=ROOT, check=True)
subprocess.run(['node', '--check', str(CLOUD)], cwd=ROOT, check=True)
subprocess.run(['git', 'diff', '--check', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)

if client == client_original or sync == sync_original or cloud == cloud_original:
    fail('one or more target files were not changed')

print('PATCH_OK')
print('Repository only; production Cloud Run NOT changed yet')
print('Changed: Client.html, RealtimeDailySync.js, cloudrun/index.js')
print('Added: QM_ASSIGN Realtime + QM Sheets/history/Telegram mirror')
print('Also completed: room-changes assignment/QM fallback fields')
print('Syntax: PASS')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)
