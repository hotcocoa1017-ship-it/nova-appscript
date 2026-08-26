from pathlib import Path
import subprocess


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# 1) Client.html: CLEANING_RESET becomes Realtime-primary, while legacy fallback
#    keeps the preserved Sheet version. Remove temporary v29 diagnostic display.
# -----------------------------------------------------------------------------
client_path = 'Client.html'
client = read(client_path)

client = replace_once(
    client,
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)",
    "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)",
    'Client Realtime action list'
)

mapped_anchor = """    const mappedAction = rawAction === 'START' ? 'CLEANING_START'\n      : rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'\n      : rawAction;\n"""
legacy_insert = mapped_anchor + """    const legacySafe = Object.assign({}, safe);\n    if (mappedAction === 'CLEANING_RESET') {\n      legacySafe.expectedVersion = Number(safe.sheetExpectedVersion || safe.expectedVersion || 0);\n    }\n    delete legacySafe.sheetExpectedVersion;\n"""
client = replace_once(client, mapped_anchor, legacy_insert, 'Client legacy Sheet version bridge')

fn_start = client.find('  async function saveRoomActionRealtimeOrLegacy_(')
fn_end = client.find('\n\n  const state = {', fn_start)
if fn_start < 0 or fn_end < 0:
    raise SystemExit('PATCH_ERROR: Client saveRoomActionRealtimeOrLegacy_ markers not found')
fn = client[fn_start:fn_end]
legacy_calls = fn.count("callServer(legacyMethod, state.token, safe)")
if legacy_calls != 3:
    raise SystemExit(f'PATCH_ERROR: Client legacy call count expected 3, found {legacy_calls}')
fn = fn.replace("callServer(legacyMethod, state.token, safe)", "callServer(legacyMethod, state.token, legacySafe)")
fn = replace_once(
    fn,
    "    safe.action = mappedAction;\n",
    "    delete safe.sheetExpectedVersion;\n    safe.action = mappedAction;\n",
    'Client remove Sheet-only version before Realtime request'
)
fn = replace_once(
    fn,
    "mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : mappedAction === 'CLEAR_ASSIGNMENT' ? '배정을 초기화했습니다.' : '청소완료 처리했습니다.'",
    "mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : mappedAction === 'CLEAR_ASSIGNMENT' ? '배정을 초기화했습니다.' : mappedAction === 'CLEANING_RESET' ? '청소완료 실적 초기화를 저장했습니다.' : '청소완료 처리했습니다.'",
    'Client CLEANING_RESET success message'
)
client = client[:fn_start] + fn + client[fn_end:]

old_version_block = """      // CLEANING_RESET remains Sheet-owned because it cancels the existing completion/history records.\n      // Realtime room.version is a DB version, so use the preserved Sheet version only for reset.\n      expectedVersion: action === 'CLEANING_RESET'\n        ? Number(room.__sheetVersion ?? room.version ?? 0)\n        : Number(room.version || 0)\n"""
new_version_block = """      // Realtime 요청은 DB version을 사용하고, Realtime 비활성/장애 시 legacy CLEANING_RESET만\n      // 별도로 보존한 Sheet version을 사용한다. 두 버전 도메인을 섞지 않는다.\n      expectedVersion: Number(room.version || 0),\n      sheetExpectedVersion: action === 'CLEANING_RESET'\n        ? Number(room.__sheetVersion ?? room.version ?? 0)\n        : 0\n"""
client = replace_once(client, old_version_block, new_version_block, 'Client CLEANING_RESET version domains')

client = replace_once(
    client,
    "      if (action === 'CLEAR_ASSIGNMENT') {\n        Object.assign(resultRoom, emptyRoomAssignmentPatch_(), { cleaningStatus: 'WAITING' });\n      }",
    "      if (action === 'CLEAR_ASSIGNMENT' || action === 'CLEANING_RESET') {\n        Object.assign(resultRoom, emptyRoomAssignmentPatch_(), { cleaningStatus: 'WAITING' });\n      }",
    'Client result room reset patch'
)

# Remove v29 diagnostic-only UI text.
diag_block = """      const resetPhases = action === 'CLEANING_RESET' ? (result.timing?.phases || {}) : {};\n      const resetTimingText = action === 'CLEANING_RESET'\n        ? ` · 조회${Number(resetPhases.historyLookupMs || 0)} · 삭제${Number(resetPhases.markHistoryDeletedMs || 0)} · 현재${Number(resetPhases.updateCurrentRoomMs || 0)} · 이력${Number(resetPhases.appendResetHistoryMs || 0)} · flush${Number(resetPhases.flushMs || 0)} · 발행${Number(resetPhases.publishVersionMs || 0)}`\n        : '';\n"""
client = replace_once(client, diag_block, '', 'Client v29 diagnostic display removal')
client = replace_once(
    client,
    "        : `${room.roomNo}호 저장 완료 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}${resetTimingText}`);",
    "        : `${room.roomNo}호 저장 완료 · 화면 ${totalMs}ms${serverMs ? ` · 서버 ${serverMs}ms` : ''}`);",
    'Client normal save status restore'
)
client = replace_once(
    client,
    "        : action === 'CLEANING_RESET'\n          ? `${room.roomNo}호 청소완료 실적 ${Number(result.resetCompletionCount || 0)}건 초기화 완료`",
    "        : action === 'CLEANING_RESET'\n          ? (result.mirrorPending === true\n              ? `${room.roomNo}호 청소완료 실적 초기화 완료 · 이력 동기화 중`\n              : `${room.roomNo}호 청소완료 실적 ${Number(result.resetCompletionCount || 0)}건 초기화 완료`)",
    'Client CLEANING_RESET mirror-pending toast'
)
write(client_path, client)


# -----------------------------------------------------------------------------
# 2) 06_Indicator.js: remove temporary v29 phase instrumentation only.
#    Keep v28 TextFinder lookup optimization and legacy reset behavior intact.
# -----------------------------------------------------------------------------
indicator_path = '06_Indicator.js'
indicator = read(indicator_path)
reset_start = indicator.find('function resetIndicatorRoomCleaningFast_(')
reset_end = indicator.find('function findIndicatorRoomActiveCleaningCompletions_(', reset_start)
if reset_start < 0 or reset_end < 0:
    raise SystemExit('PATCH_ERROR: 06_Indicator CLEANING_RESET markers not found')
reset_fn = indicator[reset_start:reset_end]
if 'const phaseTiming = {};' not in reset_fn or 'phases: phaseTiming' not in reset_fn:
    raise SystemExit('PATCH_ERROR: v29 diagnostic instrumentation not found in CLEANING_RESET')
clean_lines = []
for line in reset_fn.splitlines(True):
    if 'phaseTiming' in line or 'phaseStartedMs' in line:
        continue
    clean_lines.append(line)
reset_fn_clean = ''.join(clean_lines)
reset_fn_clean = reset_fn_clean.replace(
    "      totalMs: Math.max(0, finishedMs - startedMs),\n    }",
    "      totalMs: Math.max(0, finishedMs - startedMs)\n    }"
)
indicator = indicator[:reset_start] + reset_fn_clean + indicator[reset_end:]
if 'createTextFinder(String(businessDate || \'\').trim())' not in indicator[reset_start:reset_end + 5000]:
    raise SystemExit('VERIFY_ERROR: v28 TextFinder optimization was not preserved')
write(indicator_path, indicator)


# -----------------------------------------------------------------------------
# 3) Cloud Run: add CLEANING_RESET as a first-class room action.
# -----------------------------------------------------------------------------
cloud_path = 'cloudrun/index.js'
cloud = read(cloud_path)

cloud = replace_once(
    cloud,
    "!['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(action)",
    "!['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(action)",
    'Cloud Run action whitelist'
)

# The first CLEAR_ASSIGNMENT branch in the file is the room-changes event mapper.
mapper_old = "          if (action === 'CLEAR_ASSIGNMENT') {"
mapper_new = "          if (action === 'CLEAR_ASSIGNMENT' || action === 'CLEANING_RESET') {"
first_mapper = cloud.find(mapper_old)
route_pos = cloud.find("app.post(\n  '/v1/rooms/:roomNo/action'")
if first_mapper < 0 or route_pos < 0 or first_mapper > route_pos:
    raise SystemExit('PATCH_ERROR: Cloud Run room-changes CLEAR_ASSIGNMENT mapper not found before action route')
cloud = cloud[:first_mapper] + cloud[first_mapper:].replace(mapper_old, mapper_new, 1)

route_pos = cloud.find("app.post(\n  '/v1/rooms/:roomNo/action'")
clear_handler_pos = cloud.find("      if (action === 'CLEAR_ASSIGNMENT') {", route_pos)
if clear_handler_pos < 0:
    raise SystemExit('PATCH_ERROR: Cloud Run CLEAR_ASSIGNMENT handler marker not found')

reset_handler = r'''
      if (action === 'CLEANING_RESET') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '청소 초기화 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const previousCleaningStatus = String(room.cleaning_status || '').trim().toUpperCase();
        const resetAllowedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
        if (!resetAllowedStatuses.has(previousCleaningStatus)) {
          throw httpError(400, 'INVALID_STATE', '청소완료 상태에서만 청소초기화할 수 있습니다.');
        }

        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          resetScope: 'ALL_ACTIVE_COMPLETIONS_FOR_ROOM_DATE_SITE',
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
          mirrorPending: true,
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
cloud = cloud[:clear_handler_pos] + reset_handler + cloud[clear_handler_pos:]
write(cloud_path, cloud)


# -----------------------------------------------------------------------------
# 4) RealtimeDailySync.js: mirror CLEANING_RESET asynchronously to the exact
#    existing Sheet/history model. Pending same-batch completion rows are removed
#    before append so roommaid performance / close journals never count them.
# -----------------------------------------------------------------------------
sync_path = 'RealtimeDailySync.js'
sync = read(sync_path)
clear_marker = "      if (action === 'CLEAR_ASSIGNMENT') {"
clear_pos = sync.find(clear_marker)
if clear_pos < 0:
    raise SystemExit('PATCH_ERROR: RealtimeDailySync CLEAR_ASSIGNMENT marker not found')

sync_reset_branch = r'''      if (action === 'CLEANING_RESET') {
        const eventDetail = event.detail && typeof event.detail === 'object' ? event.detail : {};
        const previousRoomStatus = String(rowInfo.data['객실상태'] || '').trim().toUpperCase();
        const previousCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
        const previousCleaningType = String(rowInfo.data['정비유형'] || '').trim().toUpperCase();
        const previousAssignmentType = String(rowInfo.data['배정유형'] || '').trim().toUpperCase();
        const previousPrimaryEmployeeNo = String(rowInfo.data['룸메이드사번'] || '').trim();
        const previousSecondaryEmployeeNo = String(rowInfo.data['보조룸메이드사번'] || '').trim();
        const previousQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();

        // 이미 Sheet에 기록된 완료실적은 기존 CLEANING_RESET과 동일하게 소프트삭제한다.
        const historySheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
        const persistedCompletions = findIndicatorRoomActiveCleaningCompletions_(
          historySheet,
          eventBusinessDate,
          eventSite,
          eventRoomNo
        );

        // COMPLETE와 RESET이 같은 1분 미러 배치에 함께 들어온 경우,
        // 아직 Sheet에 쓰지 않은 완료이력은 historyPayloads에서 제거해 처음부터 실적에 포함시키지 않는다.
        const pendingCompletions = [];
        for (let index = historyPayloads.length - 1; index >= 0; index -= 1) {
          const item = historyPayloads[index] || {};
          if (String(item.recordType || '').trim() !== NOVA.RECORD_TYPES.CLEANING) continue;
          if (String(item.businessDate || '').trim() !== eventBusinessDate) continue;
          if (String(item.site || '').trim() !== eventSite) continue;
          if (String(item.roomNo || '').trim() !== eventRoomNo) continue;
          if (!['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(String(item.status || '').trim().toUpperCase())) continue;
          pendingCompletions.unshift(item);
          historyPayloads.splice(index, 1);
        }

        // 같은 배치에서 COMPLETE가 만든 QM 알림도 RESET 뒤에는 발송하지 않는다.
        for (let index = qmNotifications.length - 1; index >= 0; index -= 1) {
          const item = qmNotifications[index] || {};
          if (String(item.businessDate || '').trim() === eventBusinessDate
              && String(item.site || '').trim() === eventSite
              && String(item.roomNo || '').trim() === eventRoomNo) {
            qmNotifications.splice(index, 1);
          }
        }

        const resetAt = nowText_();
        if (persistedCompletions.length) {
          markIndicatorRoomCleaningCompletionsDeleted_(historySheet, persistedCompletions, resetAt);
        }

        const removedCompletionRecordIds = persistedCompletions.map(item => item.recordId).filter(Boolean);
        const removedEmployeeNos = Array.from(new Set(
          persistedCompletions.flatMap(item => [
            item.targetEmployeeNo,
            item.primaryEmployeeNo,
            item.secondaryEmployeeNo
          ]).concat(
            pendingCompletions.flatMap(item => [
              item.targetEmployeeNo,
              item.detail && item.detail.primaryEmployeeNo,
              item.detail && item.detail.secondaryEmployeeNo
            ])
          ).map(value => String(value || '').trim()).filter(Boolean)
        ));
        const removedCompletionCount = persistedCompletions.length + pendingCompletions.length;

        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: 'WAITING',
          cleaningType: '',
          assignmentType: '',
          roommaidEmployeeNo: '',
          secondaryRoommaidEmployeeNo: '',
          qmEmployeeNo: '',
          version,
          updatedAt: resetAt
        });
        rowInfo.data['청소상태'] = 'WAITING';
        rowInfo.data['정비유형'] = '';
        rowInfo.data['배정유형'] = '';
        rowInfo.data['룸메이드사번'] = '';
        rowInfo.data['보조룸메이드사번'] = '';
        rowInfo.data['QM사번'] = '';

        historyPayloads.push({
          recordType: NOVA.RECORD_TYPES.CLEANING,
          businessDate: eventBusinessDate,
          site: eventSite,
          roomNo: eventRoomNo,
          targetEmployeeNo: '',
          status: 'CLEANING_RESET',
          detail: {
            requestId,
            realtime: true,
            action: 'CLEANING_RESET',
            resetScope: String(eventDetail.resetScope || 'ALL_ACTIVE_COMPLETIONS_FOR_ROOM_DATE_SITE'),
            previousRoomStatus,
            roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
            previousCleaningStatus,
            cleaningStatus: 'WAITING',
            previousCleaningType,
            previousAssignmentType,
            previousPrimaryEmployeeNo,
            previousSecondaryEmployeeNo,
            previousQmEmployeeNo,
            removedCompletionCount,
            removedCompletionRecordIds,
            removedEmployeeNos,
            resetBy: employeeNo,
            resetAt,
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
sync = sync[:clear_pos] + sync_reset_branch + sync[clear_pos:]
write(sync_path, sync)


# -----------------------------------------------------------------------------
# Verification
# -----------------------------------------------------------------------------
client_check = read(client_path)
indicator_check = read(indicator_path)
cloud_check = read(cloud_path)
sync_check = read(sync_path)

checks = [
    ("'CLEANING_RESET', 'ASSIGN_ROOMMAID'" in client_check, 'Client Realtime CLEANING_RESET missing'),
    ('sheetExpectedVersion' in client_check, 'Client Sheet-version fallback missing'),
    ('resetTimingText' not in client_check, 'Client v29 diagnostic display still present'),
    ('phaseTiming' not in indicator_check[reset_start:reset_end], '06_Indicator v29 diagnostic remains'),
    ("createTextFinder(String(businessDate || '').trim())" in indicator_check, '06_Indicator v28 TextFinder missing'),
    ("'CLEANING_RESET', 'ASSIGN_ROOMMAID'" in cloud_check, 'Cloud Run CLEANING_RESET whitelist missing'),
    ("if (action === 'CLEANING_RESET')" in cloud_check, 'Cloud Run CLEANING_RESET handler missing'),
    ('mirrorPending: true' in cloud_check, 'Cloud Run CLEANING_RESET mirrorPending missing'),
    ("if (action === 'CLEANING_RESET')" in sync_check, 'RealtimeDailySync CLEANING_RESET mirror missing'),
    ("status: 'CLEANING_RESET'" in sync_check, 'RealtimeDailySync CLEANING_RESET history missing'),
]
for ok, message in checks:
    if not ok:
        raise SystemExit('VERIFY_ERROR: ' + message)

# Syntax-check production Cloud Run file.
subprocess.run(['node', '--check', cloud_path], check=True)

print('PATCH_OK')
print('Repository only; production Cloud Run / Apps Script NOT changed yet')
print('Changed: Client.html, 06_Indicator.js, RealtimeDailySync.js, cloudrun/index.js')
print('Added: CLEANING_RESET Realtime primary save + 1-minute Sheet/history mirror')
print('Preserved: v26 Sheet-version fallback, v28 TextFinder lookup, reset eligibility, completion soft-delete, roommaid performance/close exclusion, permissions')
print('Removed: temporary v29 phase diagnostic code/display')
print('Cloud Run syntax: PASS')
print('VERIFY: PASS')
