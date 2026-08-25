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
# Client: UPDATE_OPERATION_FLAGS uses Realtime primary save.
# Flags remain optional partial Realtime fields, so full DB room hydration cannot
# overwrite Sheet-owned values when the DB row itself does not contain these columns.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')

client = replace_once(
    client,
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'version', 'updatedAt'",
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'",
    'Client optional Realtime operation flag fields'
)

partial_anchor = """    putText('operationalStatus', 'operational_status', 'operationalStatus');
    if (hasOwn('version')) mapped.version = Number(row.version || 0);"""
partial_insert = """    putText('operationalStatus', 'operational_status', 'operationalStatus');
    if (hasOwn('preassigned')) mapped.preassigned = row.preassigned === true;
    if (hasOwn('vip')) mapped.vip = row.vip === true;
    if (hasOwn('important_room') || hasOwn('importantRoom')) mapped.importantRoom = (row.important_room ?? row.importantRoom) === true;
    if (hasOwn('version')) mapped.version = Number(row.version || 0);"""
client = replace_once(client, partial_anchor, partial_insert, 'Client partial operation flag mapping')

client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS'].includes(mappedAction)",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS'].includes(mappedAction)",
    'Client operation flags realtime routing'
)

client = replace_once(
    client,
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : '청소완료 처리했습니다.');",
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : '청소완료 처리했습니다.');",
    'Client operation flags result message'
)

# -----------------------------------------------------------------------------
# RealtimeDailySync: write DB event back into existing Sheet columns/history.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
sync_anchor = "      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {"
if sync.count(sync_anchor) != 1:
    fail(f'RealtimeDailySync operational-status anchor: expected 1 match, found {sync.count(sync_anchor)}')

sync_branch = r'''      if (action === 'UPDATE_OPERATION_FLAGS') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const preassigned = eventDetail.preassigned === true;
        const vip = eventDetail.vip === true;
        const importantRoom = eventDetail.importantRoom === true;

        ensureRoomOperationalFlagHeaders_();
        const updates = {
          '선배정여부': preassigned ? 'Y' : 'N',
          'VIP여부': vip ? 'Y' : 'N',
          '중요객실여부': importantRoom ? 'Y' : 'N',
          '수정일시': nowText_(),
          '마지막변경버전': version
        };
        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'UPDATE_OPERATION_FLAGS',
          detail: {
            requestId,
            realtime: true,
            action: 'UPDATE_OPERATION_FLAGS',
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
            cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
            assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
            primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
            creditUnit: getRoommaidCleaningCreditUnit_(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
            preassigned,
            vip,
            importantRoom,
            previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
            operationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),
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
sync = sync.replace(sync_anchor, sync_branch + sync_anchor, 1)

# -----------------------------------------------------------------------------
# Cloud Run: event-first flag save. No schema migration is required:
# room row version is advanced, flags travel in event detail and Sheet remains
# durable source until mirrored. Requester UI is already optimistic.
# -----------------------------------------------------------------------------
cloud = CLOUD.read_text(encoding='utf-8')

cloud = replace_once(
    cloud,
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS'].includes(action)",
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS'].includes(action)",
    'Cloud Run allowed operation flags action'
)

changes_anchor = """          if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
            delete room.cleaningStatus;
            room.operationalStatus = String("""
if cloud.count(changes_anchor) != 1:
    fail(f'Cloud Run room-changes operational mapping anchor: expected 1 match, found {cloud.count(changes_anchor)}')
changes_branch = r'''          if (action === 'UPDATE_OPERATION_FLAGS') {
            delete room.cleaningStatus;
            room.preassigned = detail.preassigned === true;
            room.vip = detail.vip === true;
            room.importantRoom = detail.importantRoom === true;
          }
'''
cloud = cloud.replace(changes_anchor, changes_branch + changes_anchor, 1)

route_start_marker = "app.post(\n  '/v1/rooms/:roomNo/action',"
route_end_marker = "\napp.post(\n  '/v1/houseman-orders',"
route_start = cloud.find(route_start_marker)
if route_start < 0:
    fail('Cloud Run room action route start not found')
route_end = cloud.find(route_end_marker, route_start)
if route_end < 0:
    fail('Cloud Run room action route end not found')
route_segment = cloud[route_start:route_end]
route_anchor = "      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {"
if route_segment.count(route_anchor) != 1:
    fail(f'Cloud Run operational-status route anchor inside room-action route: expected 1 match, found {route_segment.count(route_anchor)}')

route_branch = r'''      if (action === 'UPDATE_OPERATION_FLAGS') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '객실 운영표시 변경 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const preassigned = body.preassigned === true;
        const vip = body.vip === true;
        const importantRoom = body.importantRoom === true;

        const updated = await client.query(
          `update public.nova_rooms_current
              set version=version+1,
                  updated_by=$4,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [businessDate, site, roomNo, user.employee_no]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          preassigned,
          vip,
          importantRoom
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
            '',
            '',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const responseRoom = {
          ...roomDto(nextRoom),
          preassigned,
          vip,
          importantRoom
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
route_segment = route_segment.replace(route_anchor, route_branch + route_anchor, 1)
cloud = cloud[:route_start] + route_segment + cloud[route_end:]

# Backups and writes.
for path in (CLIENT, SYNC, CLOUD):
    backup = path.with_name(path.name + '.backup_before_v24')
    if not backup.exists():
        backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')

CLIENT.write_text(client, encoding='utf-8')
SYNC.write_text(sync, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')

# Validation.
subprocess.run(['node', '--check', str(CLOUD)], cwd=ROOT, check=True)
client_text = CLIENT.read_text(encoding='utf-8')
start = client_text.find('<script>')
end = client_text.rfind('</script>')
if start < 0 or end <= start:
    fail('Client embedded script not found')
tmp = ROOT / '.tmp_client_v24.js'
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
print('Added: UPDATE_OPERATION_FLAGS Realtime (preassigned / VIP / important room)')
print('No DB schema migration required; flags mirror to existing Sheet columns/history')
print('Preserved: existing optimistic UI, permissions, all other room actions')
print('Syntax: PASS')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)
