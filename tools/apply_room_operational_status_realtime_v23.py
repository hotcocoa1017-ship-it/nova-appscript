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
# Client: UPDATE_ROOM_OPERATION_STATUS -> Realtime primary save.
# Existing optimistic UI is preserved; only the persistence route changes.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')

client = replace_once(
    client,
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'version', 'updatedAt'",
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'version', 'updatedAt'",
    'Client realtime owned operationalStatus field'
)

client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN'].includes(mappedAction)\n      || (mappedAction === 'CHANGE_ROOM_STATUS'\n        && String(safe.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT');",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS'].includes(mappedAction)\n      || (mappedAction === 'CHANGE_ROOM_STATUS'\n        && String(safe.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT');",
    'Client operational status realtime routing'
)

client = replace_once(
    client,
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : '청소완료 처리했습니다.');",
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : '청소완료 처리했습니다.');",
    'Client operational status result message'
)

# -----------------------------------------------------------------------------
# RealtimeDailySync: mirror DB operational-status events into the existing Sheet
# and unified history structure. No UI/business-rule rewrite.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
status_anchor = "      if (action === 'CHANGE_ROOM_STATUS') {"
if sync.count(status_anchor) != 1:
    fail(f'RealtimeDailySync CHANGE_ROOM_STATUS anchor: expected 1 match, found {sync.count(status_anchor)}')

operational_branch = r'''      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const rawOperationalStatus = String(
          Object.prototype.hasOwnProperty.call(eventDetail, 'operationalStatus')
            ? eventDetail.operationalStatus
            : event.afterStatus || ''
        ).trim();
        const requestedOperationalStatus = normalizeIndicatorRoomOperationalStatus_(rawOperationalStatus);
        if (rawOperationalStatus && !requestedOperationalStatus) {
          throw new Error(`DB 객실 조치상태 이벤트 값이 올바르지 않습니다. (${eventSite} ${eventRoomNo}호)`);
        }

        ensureIndicatorRoomOperationalStatusHeader_();
        const previousOperationalStatus = normalizeIndicatorRoomOperationalStatus_(
          rowInfo.data[indicatorRoomOperationalStatusHeader_()]
        );
        const updates = {
          '수정일시': nowText_(),
          '마지막변경버전': version
        };
        updates[indicatorRoomOperationalStatusHeader_()] = requestedOperationalStatus;
        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.ADMIN_SETTING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'UPDATE_ROOM_OPERATION_STATUS',
          detail: {
            requestId,
            realtime: true,
            action: 'UPDATE_ROOM_OPERATION_STATUS',
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
            cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
            assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
            primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
            creditUnit: getRoommaidCleaningCreditUnit_(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
            previousOperationalStatus,
            operationalStatus: requestedOperationalStatus,
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
sync = sync.replace(status_anchor, operational_branch + status_anchor, 1)

# -----------------------------------------------------------------------------
# Cloud Run: add UPDATE_ROOM_OPERATION_STATUS to the existing room action route.
# Canonical values are exactly the existing Apps Script values: BROKEN, ROOM_CHECK, ''.
# -----------------------------------------------------------------------------
cloud = CLOUD.read_text(encoding='utf-8')

cloud = replace_once(
    cloud,
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS'].includes(action)",
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS'].includes(action)",
    'Cloud Run allowed operational status action'
)

changes_anchor = """          if (action === 'CHANGE_ROOM_STATUS') {
            delete room.cleaningStatus;
"""
if cloud.count(changes_anchor) != 1:
    fail(f'Cloud Run room-changes status mapping anchor: expected 1 match, found {cloud.count(changes_anchor)}')
changes_insert = r'''          if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
            delete room.cleaningStatus;
            room.operationalStatus = String(
              Object.prototype.hasOwnProperty.call(detail, 'operationalStatus')
                ? detail.operationalStatus
                : row.after_status || ''
            );
          }
'''
cloud = cloud.replace(changes_anchor, changes_insert + changes_anchor, 1)

route_anchor = "      if (action === 'CHANGE_ROOM_STATUS') {"
if cloud.count(route_anchor) != 1:
    fail(f'Cloud Run CHANGE_ROOM_STATUS route anchor: expected 1 match, found {cloud.count(route_anchor)}')

route_branch = r'''      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '객실 조치상태 변경 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const rawOperationalStatus = cleanText_(body.operationalStatus, 40).toUpperCase();
        const operationalStatus = rawOperationalStatus === ''
          ? ''
          : (['BROKEN', 'OUT_OF_ORDER', 'OOO', 'O.O.O', '0.0.0'].includes(rawOperationalStatus)
              ? 'BROKEN'
              : (['ROOM_CHECK', 'ROOMCHECK', 'CHECK_ROOM'].includes(rawOperationalStatus)
                  ? 'ROOM_CHECK'
                  : ''));
        if (rawOperationalStatus && !operationalStatus) {
          throw httpError(400, 'INVALID_OPERATIONAL_STATUS', '사용할 수 없는 객실 조치상태입니다.');
        }

        const previousOperationalStatus = String(room.operational_status || '').trim().toUpperCase();
        if (previousOperationalStatus === operationalStatus) {
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

        const updated = await client.query(
          `update public.nova_rooms_current
              set operational_status=nullif($4,''),
                  version=version+1,
                  updated_by=$5,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [businessDate, site, roomNo, operationalStatus, user.employee_no]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          previousOperationalStatus,
          operationalStatus
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
            previousOperationalStatus,
            operationalStatus,
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
cloud = cloud.replace(route_anchor, route_branch + route_anchor, 1)

# Save backups only once, then write repository snapshots.
for path in (CLIENT, SYNC, CLOUD):
    backup = path.with_name(path.name + '.backup_before_v23')
    if not backup.exists():
        backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')

CLIENT.write_text(client, encoding='utf-8')
SYNC.write_text(sync, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')

# Validate JS/HTML embedded JS and whitespace before any production deployment.
subprocess.run(['node', '--check', str(CLOUD)], cwd=ROOT, check=True)
client_text = CLIENT.read_text(encoding='utf-8')
start = client_text.find('<script>')
end = client_text.rfind('</script>')
if start < 0 or end <= start:
    fail('Client embedded script not found')
tmp = ROOT / '.tmp_client_v23.js'
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
print('Added: UPDATE_ROOM_OPERATION_STATUS Realtime (BROKEN / ROOM_CHECK / clear)')
print('Preserved: existing optimistic UI, permissions, Sheet/history mirror, other room actions')
print('Syntax: PASS')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=ROOT, check=True)
