#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
CLIENT = REPO / 'Client.html'
SYNC = REPO / 'RealtimeDailySync.js'
CLOUD = REPO / 'cloudrun' / 'index.js'


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
# Client: general room status changes (except CHECKED_OUT) use Realtime.
# Existing CHECKED_OUT fast legacy path is intentionally preserved for now.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')

client = replace_once(
    client,
    "    'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'version', 'updatedAt'",
    "    'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'version', 'updatedAt'",
    'Client realtime owned roomStatus field'
)

client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN'].includes(mappedAction);",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN'].includes(mappedAction)\n      || (mappedAction === 'CHANGE_ROOM_STATUS'\n        && String(safe.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT');",
    'Client general room status realtime routing'
)

# Preserve the exact optimistic state that the current UI already computes, and send only DB-owned fields.
client = replace_once(
    client,
    "    const optimisticPatch = buildOptimisticRoomPatch_(room, payload);\n    const fastAction = Boolean(optimisticPatch);",
    "    const optimisticPatch = buildOptimisticRoomPatch_(room, payload);\n    if (action === 'CHANGE_ROOM_STATUS'\n        && String(payload.roomStatus || '').trim().toUpperCase() !== 'CHECKED_OUT'\n        && optimisticPatch) {\n      const realtimeRoomPatch = {};\n      [\n        'cleaningStatus', 'cleaningType', 'assignmentType',\n        'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo'\n      ].forEach(key => {\n        if (Object.prototype.hasOwnProperty.call(optimisticPatch, key)) {\n          realtimeRoomPatch[key] = optimisticPatch[key];\n        }\n      });\n      payload.realtimeRoomPatch = realtimeRoomPatch;\n    }\n    const fastAction = Boolean(optimisticPatch);",
    'Client status optimistic DB patch payload'
)

client = replace_once(
    client,
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : '청소완료 처리했습니다.');",
    "    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : '청소완료 처리했습니다.');",
    'Client room status result message'
)

# -----------------------------------------------------------------------------
# RealtimeDailySync: mirror CHANGE_ROOM_STATUS using the exact existing Apps
# Script business rules/helpers instead of duplicating those rules in Cloud Run.
# -----------------------------------------------------------------------------
sync = SYNC.read_text(encoding='utf-8')
status_anchor = """      roomUpdates.push({
        rowNumber: rowInfo.rowNumber,
        cleaningStatus: afterStatus,
        version,
        updatedAt: nowText_()
      });
"""
if sync.count(status_anchor) != 1:
    fail(f'RealtimeDailySync status insertion anchor: expected 1 match, found {sync.count(status_anchor)}')

status_branch = r'''      if (action === 'CHANGE_ROOM_STATUS') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const requestedRoomStatus = String(eventDetail.roomStatus || event.afterStatus || '').trim().toUpperCase();
        if (!requestedRoomStatus) {
          throw new Error(`DB 객실상태 변경 이벤트에 상태값이 없습니다. (${eventSite} ${eventRoomNo}호)`);
        }

        const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
        const updates = {
          '수정일시': nowText_(),
          '마지막변경버전': version
        };

        if (isNovaRoomCleaningTargetStatus_(requestedRoomStatus)) {
          Object.assign(updates, buildIndicatorPreviousCycleArchiveUpdates_(rowInfo.data));
        }
        updates['객실상태'] = requestedRoomStatus;
        updates[indicatorLastRoomStatusHeader_()] = resolveIndicatorLastRoomStatusAfterChange_(requestedRoomStatus, rowInfo.data);
        if (requestedRoomStatus === 'VACANT_CLEAN') {
          indicatorPreviousCycleHeaders_().forEach(header => { updates[header] = ''; });
        }
        Object.assign(updates, resolveManualRoomStatusState_(requestedRoomStatus, rowInfo.data));

        updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);
        Object.assign(rowInfo.data, updates);

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.ROOM_STATUS_CHANGE,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'CHANGE_ROOM_STATUS',
          detail: {
            requestId,
            realtime: true,
            action: 'CHANGE_ROOM_STATUS',
            previousRoomStatus,
            roomStatus: requestedRoomStatus,
            specialDepartureStarted: isNovaSpecialDepartureStatus_(requestedRoomStatus)
              && requestedRoomStatus !== previousRoomStatus,
            cleaningStatus: String(rowInfo.data['청소상태'] || '').trim(),
            cleaningType: String(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL).trim().toUpperCase(),
            assignmentType: String(rowInfo.data['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO).trim().toUpperCase(),
            primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
            creditUnit: getRoommaidCleaningCreditUnit_(rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
            preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
            vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
            importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
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
sync = sync.replace(status_anchor, status_branch + status_anchor, 1)

# -----------------------------------------------------------------------------
# Cloud Run repository snapshot: add CHANGE_ROOM_STATUS before canCleanRoom.
# CHECKED_OUT remains on the existing Apps Script fast path.
# -----------------------------------------------------------------------------
cloud = CLOUD.read_text(encoding='utf-8')

cloud = replace_once(
    cloud,
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN'].includes(action)",
    "        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS'].includes(action)",
    'Cloud Run allowed room actions'
)

# room-changes fallback must not misinterpret room-status events as cleaning-status events.
changes_anchor = """          if (action === 'ASSIGN_ROOMMAID') {
            room.cleaningType = String(detail.cleaningType || 'NORMAL');
"""
if cloud.count(changes_anchor) != 1:
    fail(f'Cloud Run room-changes mapping anchor: expected 1 match, found {cloud.count(changes_anchor)}')
changes_insert = r'''          if (action === 'CHANGE_ROOM_STATUS') {
            delete room.cleaningStatus;
            room.roomStatus = String(detail.roomStatus || row.after_status || '');
            const roomPatch = detail.roomPatch && typeof detail.roomPatch === 'object' ? detail.roomPatch : {};
            [
              'cleaningStatus', 'cleaningType', 'assignmentType',
              'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo'
            ].forEach(key => {
              if (Object.prototype.hasOwnProperty.call(roomPatch, key)) room[key] = roomPatch[key];
            });
          }
'''
cloud = cloud.replace(changes_anchor, changes_insert + changes_anchor, 1)

# Insert general room status branch immediately before existing QM_ASSIGN branch.
qm_anchor = "      if (action === 'QM_ASSIGN') {"
if cloud.count(qm_anchor) != 1:
    fail(f'Cloud Run QM branch anchor: expected 1 match, found {cloud.count(qm_anchor)}')
status_route = r'''      if (action === 'CHANGE_ROOM_STATUS') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '객실상태 변경 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const requestedRoomStatus = cleanText_(body.roomStatus, 40).toUpperCase();
        if (!requestedRoomStatus) {
          throw httpError(400, 'ROOM_STATUS_REQUIRED', '변경할 객실상태를 선택하세요.');
        }
        if (requestedRoomStatus === 'CHECKED_OUT') {
          throw httpError(400, 'CHECKOUT_LEGACY_ONLY', '퇴실은 기존 전용 저장경로를 사용합니다.');
        }

        const rawPatch = body.realtimeRoomPatch && typeof body.realtimeRoomPatch === 'object'
          ? body.realtimeRoomPatch
          : {};
        const hasOwn = key => Object.prototype.hasOwnProperty.call(rawPatch, key);
        const cleaningStatus = hasOwn('cleaningStatus')
          ? cleanText_(rawPatch.cleaningStatus || 'WAITING', 40).toUpperCase()
          : String(room.cleaning_status || 'WAITING').toUpperCase();
        const cleaningType = hasOwn('cleaningType')
          ? cleanText_(rawPatch.cleaningType || 'NORMAL', 40).toUpperCase()
          : String(room.cleaning_type || 'NORMAL').toUpperCase();
        const assignmentType = hasOwn('assignmentType')
          ? cleanText_(rawPatch.assignmentType || 'SOLO', 40).toUpperCase()
          : String(room.assignment_type || 'SOLO').toUpperCase();
        const roommaidEmployeeNo = hasOwn('roommaidEmployeeNo')
          ? cleanText_(rawPatch.roommaidEmployeeNo, 80)
          : String(room.roommaid_employee_no || '');
        const secondaryRoommaidEmployeeNo = hasOwn('secondaryRoommaidEmployeeNo')
          ? cleanText_(rawPatch.secondaryRoommaidEmployeeNo, 80)
          : String(room.secondary_roommaid_employee_no || '');
        const qmEmployeeNo = hasOwn('qmEmployeeNo')
          ? cleanText_(rawPatch.qmEmployeeNo, 80)
          : String(room.qm_employee_no || '');

        const roomPatch = {
          cleaningStatus,
          cleaningType,
          assignmentType,
          roommaidEmployeeNo,
          secondaryRoommaidEmployeeNo,
          qmEmployeeNo
        };

        const sameState = String(room.room_status || '').toUpperCase() === requestedRoomStatus
          && String(room.cleaning_status || 'WAITING').toUpperCase() === cleaningStatus
          && String(room.cleaning_type || 'NORMAL').toUpperCase() === cleaningType
          && String(room.assignment_type || 'SOLO').toUpperCase() === assignmentType
          && String(room.roommaid_employee_no || '') === roommaidEmployeeNo
          && String(room.secondary_roommaid_employee_no || '') === secondaryRoommaidEmployeeNo
          && String(room.qm_employee_no || '') === qmEmployeeNo;

        if (sameState) {
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

        const previousRoomStatus = String(room.room_status || '');
        const updated = await client.query(
          `update public.nova_rooms_current
              set room_status=$4,
                  cleaning_status=$5,
                  cleaning_type=$6,
                  assignment_type=$7,
                  roommaid_employee_no=nullif($8,''),
                  secondary_roommaid_employee_no=nullif($9,''),
                  qm_employee_no=nullif($10,''),
                  version=version+1,
                  updated_by=$11,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [
            businessDate,
            site,
            roomNo,
            requestedRoomStatus,
            cleaningStatus,
            cleaningType,
            assignmentType,
            roommaidEmployeeNo,
            secondaryRoommaidEmployeeNo,
            qmEmployeeNo,
            user.employee_no
          ]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          roomStatus: requestedRoomStatus,
          roomPatch
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
            previousRoomStatus,
            requestedRoomStatus,
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
cloud = cloud.replace(qm_anchor, status_route + qm_anchor, 1)

# Save guarded backups and patched repository snapshots only.
backup(CLIENT, '.backup_v21_before_room_status_v22')
backup(SYNC, '.backup_v21_before_room_status_v22')
backup(CLOUD, '.backup_v21_before_room_status_v22')
CLIENT.write_text(client, encoding='utf-8')
SYNC.write_text(sync, encoding='utf-8')
CLOUD.write_text(cloud, encoding='utf-8')

# Syntax + diff guard rails. Client.html is HTML, so check embedded script indirectly via diff only.
subprocess.run(['node', '--check', str(SYNC)], cwd=REPO, check=True)
subprocess.run(['node', '--check', str(CLOUD)], cwd=REPO, check=True)
subprocess.run(['git', 'diff', '--check', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=REPO, check=True)

print('PATCH_OK')
print('Repository only; production Cloud Run NOT changed yet')
print('Changed: Client.html, RealtimeDailySync.js, cloudrun/index.js')
print('Added: CHANGE_ROOM_STATUS Realtime (CHECKED_OUT intentionally preserved on existing fast path)')
print('Preserved: existing status business rules via Apps Script mirror helpers')
print('Syntax: PASS')
subprocess.run(['git', 'diff', '--stat', '--', 'Client.html', 'RealtimeDailySync.js', 'cloudrun/index.js'], cwd=REPO, check=True)
