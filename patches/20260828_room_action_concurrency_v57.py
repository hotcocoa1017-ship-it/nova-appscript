from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'
CLOUD = ROOT / 'cloudrun' / 'index.js'
QM = ROOT / '16_QmChecklist.js'
MOBILE = ROOT / '10_Mobile.js'
INDICATOR = ROOT / '06_Indicator.js'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# 1) Client: keep DB version and Sheet version separate on every legacy fallback,
#    and send an action-scoped expected state snapshot to Cloud Run.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')

old = """    const legacySafe = Object.assign({}, safe);\n    if (mappedAction === 'CLEANING_RESET') {\n      legacySafe.expectedVersion = Number(safe.sheetExpectedVersion || safe.expectedVersion || 0);\n    }\n    delete legacySafe.sheetExpectedVersion;\n"""
new = """    const legacySafe = Object.assign({}, safe);\n    // Realtime room.version(DB)과 Sheet 마지막변경버전은 서로 다른 버전 도메인이다.\n    // Apps Script legacy 경로(퇴실 포함)로 내려갈 때는 항상 별도 보존한 Sheet version을 사용한다.\n    if (Number(safe.sheetExpectedVersion || 0) > 0) {\n      legacySafe.expectedVersion = Number(safe.sheetExpectedVersion || 0);\n    }\n    delete legacySafe.sheetExpectedVersion;\n"""
client = replace_once(client, old, new, 'legacy Sheet version routing')

old = """      expectedVersion: action === 'CLEAR_ASSIGNMENT' ? 0 : Number(room.version || 0),\n      sheetExpectedVersion: action === 'CLEANING_RESET'\n        ? Number(room.__sheetVersion ?? room.version ?? 0)\n        : 0\n"""
new = """      expectedVersion: action === 'CLEAR_ASSIGNMENT' ? 0 : Number(room.version || 0),\n      // Cloud Run은 DB version을 사용하되, version이 달라졌을 때 실제로 이 작업과\n      // 충돌하는 필드가 바뀌었는지 expectedState로 한 번 더 판정한다.\n      expectedState: {\n        roomStatus: String(room.roomStatus || ''),\n        cleaningStatus: String(room.cleaningStatus || ''),\n        cleaningType: String(room.cleaningType || 'NORMAL'),\n        assignmentType: String(room.assignmentType || 'SOLO'),\n        roommaidEmployeeNo: String(room.roommaidEmployeeNo || ''),\n        secondaryRoommaidEmployeeNo: String(room.secondaryRoommaidEmployeeNo || ''),\n        qmEmployeeNo: String(room.qmEmployeeNo || ''),\n        operationalStatus: String(room.operationalStatus || '')\n      },\n      // Realtime 비활성/legacy 퇴실 경로에서는 반드시 Sheet version을 사용한다.\n      sheetExpectedVersion: Number(room.__sheetVersion ?? room.version ?? 0)\n"""
client = replace_once(client, old, new, 'room action expected state payload')
CLIENT.write_text(client, encoding='utf-8')


# -----------------------------------------------------------------------------
# 2) Cloud Run: PostgreSQL FOR UPDATE remains the serialization primitive.
#    A row-version mismatch is rejected only when the fields relevant to the
#    requested action actually changed. Unrelated changes no longer create a
#    false VERSION_CONFLICT.
# -----------------------------------------------------------------------------
cloud = CLOUD.read_text(encoding='utf-8')
helper_anchor = "const HOUSEMAN_STATUS_LABELS_ = Object.freeze({"
if helper_anchor not in cloud:
    fail('Cloud Run helper anchor not found')

helper = r"""
function roomActionExpectedStateMatches_(action, expectedState, room) {
  if (!expectedState || typeof expectedState !== 'object' || !room) return false;

  const upper = value => String(value ?? '').trim().toUpperCase();
  const actual = {
    roomStatus: upper(room.room_status),
    cleaningStatus: upper(room.cleaning_status),
    cleaningType: upper(room.cleaning_type || 'NORMAL'),
    assignmentType: upper(room.assignment_type || 'SOLO'),
    roommaidEmployeeNo: String(room.roommaid_employee_no || '').trim(),
    secondaryRoommaidEmployeeNo: String(room.secondary_roommaid_employee_no || '').trim(),
    qmEmployeeNo: String(room.qm_employee_no || '').trim(),
    operationalStatus: upper(room.operational_status)
  };
  const expected = {
    roomStatus: upper(expectedState.roomStatus),
    cleaningStatus: upper(expectedState.cleaningStatus),
    cleaningType: upper(expectedState.cleaningType || 'NORMAL'),
    assignmentType: upper(expectedState.assignmentType || 'SOLO'),
    roommaidEmployeeNo: String(expectedState.roommaidEmployeeNo || '').trim(),
    secondaryRoommaidEmployeeNo: String(expectedState.secondaryRoommaidEmployeeNo || '').trim(),
    qmEmployeeNo: String(expectedState.qmEmployeeNo || '').trim(),
    operationalStatus: upper(expectedState.operationalStatus)
  };

  const actionKey = String(action || '').trim().toUpperCase();
  const fieldsByAction = {
    ASSIGN_ROOMMAID: [
      'cleaningStatus', 'cleaningType', 'assignmentType',
      'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo'
    ],
    CLEANING_RESET: [
      'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType',
      'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo'
    ],
    QM_ASSIGN: ['cleaningStatus', 'qmEmployeeNo'],
    CHANGE_ROOM_STATUS: [
      'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType',
      'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo'
    ],
    UPDATE_ROOM_OPERATION_STATUS: ['operationalStatus']
  };
  const fields = fieldsByAction[actionKey] || [];
  return fields.length > 0 && fields.every(key => actual[key] === expected[key]);
}

function assertRoomActionVersion_(action, expectedVersion, expectedState, room) {
  const expected = Number(expectedVersion || 0);
  const actual = Number(room?.version || 0);
  if (expected <= 0 || expected === actual) return;

  const actionKey = String(action || '').trim().toUpperCase();

  // 룸메이드 청소 진행은 DB row-lock + 실제 배정자 + 현재 청소상태 검증이 더 정확하다.
  // VIP/객실상태/운영표시 같은 독립 필드 변경 때문에 청소가 막히지 않게 한다.
  if (['CLEANING_START', 'CLEANING_COMPLETE'].includes(actionKey)) return;

  // 운영표시는 현재 DB에서 이벤트 기반으로 보존되는 독립 도메인이다.
  // 동일 객실의 청소/배정 version 증가와 결합시키지 않는다.
  if (actionKey === 'UPDATE_OPERATION_FLAGS') return;

  // 배정초기화는 현재 상태를 '없음'으로 만드는 멱등 작업이며 Client도 version=0으로 요청한다.
  if (actionKey === 'CLEAR_ASSIGNMENT') return;

  // 같은 객실이라도 이 작업이 다루는 필드가 그대로라면 unrelated version bump이므로 허용한다.
  if (roomActionExpectedStateMatches_(actionKey, expectedState, room)) return;

  throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
    currentRoom: roomDto(room)
  });
}

"""
if 'function assertRoomActionVersion_(' not in cloud:
    cloud = cloud.replace(helper_anchor, helper + helper_anchor, 1)

inline_old = """        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {\n          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {\n            currentRoom: roomDto(room)\n          });\n        }\n"""
inline_count = cloud.count(inline_old)
if inline_count != 7:
    fail(f'Cloud Run inline version guards: expected 7, found {inline_count}')
cloud = cloud.replace(
    inline_old,
    "        assertRoomActionVersion_(action, expectedVersion, body.expectedState, room);\n"
)

multiline_old = """      if (\n        expectedVersion > 0\n        && expectedVersion\n          !== Number(room.version)\n      ) {\n\n        throw httpError(\n          409,\n          'VERSION_CONFLICT',\n          '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.',\n          {\n            currentRoom:\n              roomDto(room)\n          }\n        );\n      }\n"""
cloud = replace_once(
    cloud,
    multiline_old,
    "      assertRoomActionVersion_(action, expectedVersion, body.expectedState, room);\n",
    'Cloud Run cleaning version guard'
)
CLOUD.write_text(cloud, encoding='utf-8')


# -----------------------------------------------------------------------------
# 3) QM checklist: the Sheet global version is too coarse. Keep the short lock,
#    but use assignment + cleaning-state preconditions as the conflict guard.
#    This rejects real same-room workflow changes and accepts unrelated version
#    bumps from DB mirrors or flags.
# -----------------------------------------------------------------------------
qm = QM.read_text(encoding='utf-8')
qm_guard = "    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n"
qm_count = qm.count(qm_guard)
if qm_count != 2:
    fail(f'QM version guards: expected 2, found {qm_count}')
qm = qm.replace(
    qm_guard,
    "    // QM은 본인 배정 여부와 청소상태를 잠금 안에서 다시 검증하므로, DB 미러 등 독립 변경의\n"
    "    // Sheet 전체버전 증가만으로 정상 점검을 거절하지 않는다. 실제 흐름 변경은 아래 상태검증이 차단한다.\n"
)
QM.write_text(qm, encoding='utf-8')


# -----------------------------------------------------------------------------
# 4) QM mobile REWORK legacy path: same principle as checklist start/submit.
#    ROOMMAID legacy behavior is unchanged; Realtime ROOMMAID is already v56.
# -----------------------------------------------------------------------------
mobile = MOBILE.read_text(encoding='utf-8')
mobile_old = "    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n"
mobile_new = """    // QM은 아래의 본인배정 검증과 작업상태 검증을 원본으로 사용한다.\n    // Sheet 전체버전은 Realtime 미러 등 독립 변경에도 증가하므로 QM 작업에는 직접 충돌키로 쓰지 않는다.\n    if (role !== 'QM') {\n      assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n    }\n"""
mobile = replace_once(mobile, mobile_old, mobile_new, 'QM mobile semantic version guard')
MOBILE.write_text(mobile, encoding='utf-8')


# -----------------------------------------------------------------------------
# 5) Legacy CHECKED_OUT is intentionally Sheet-owned. When its Sheet version is
#    stale only because an unrelated field changed, compare the checkout-relevant
#    room state before declaring a conflict.
# -----------------------------------------------------------------------------
indicator = INDICATOR.read_text(encoding='utf-8')
checkout_marker = 'function changeIndicatorRoomCheckoutFast_'
checkout_start = indicator.find(checkout_marker)
if checkout_start < 0:
    fail('checkout fast function not found')
checkout_end = indicator.find('\nfunction ', checkout_start + len(checkout_marker))
if checkout_end < 0:
    checkout_end = len(indicator)
checkout_segment = indicator[checkout_start:checkout_end]
checkout_guard = "    assertExpectedVersion_(safe.expectedVersion, rowInfo.data['마지막변경버전'], `${roomNo}호 객실`);\n"
if checkout_segment.count(checkout_guard) != 1:
    fail(f'checkout version guard expected 1, found {checkout_segment.count(checkout_guard)}')
checkout_replacement = """    assertIndicatorCheckoutExpectedState_(safe, rowInfo.data, roomNo);\n"""
checkout_segment = checkout_segment.replace(checkout_guard, checkout_replacement, 1)
indicator = indicator[:checkout_start] + checkout_segment + indicator[checkout_end:]

checkout_helper = r"""
function assertIndicatorCheckoutExpectedState_(safe, rowData, roomNo) {
  const expectedVersion = Number(safe && safe.expectedVersion || 0);
  const actualVersion = Number(rowData && rowData['마지막변경버전'] || 0);
  if (expectedVersion <= 0 || expectedVersion === actualVersion) return;

  const expected = safe && safe.expectedState && typeof safe.expectedState === 'object'
    ? safe.expectedState
    : null;
  if (expected) {
    const upper = value => String(value ?? '').trim().toUpperCase();
    const actual = {
      roomStatus: upper(rowData['객실상태']),
      cleaningStatus: upper(rowData['청소상태']),
      cleaningType: upper(rowData['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
      assignmentType: upper(rowData['배정유형'] || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO),
      roommaidEmployeeNo: String(rowData['룸메이드사번'] || '').trim(),
      secondaryRoommaidEmployeeNo: String(rowData['보조룸메이드사번'] || '').trim(),
      qmEmployeeNo: String(rowData['QM사번'] || '').trim()
    };
    const expectedNormalized = {
      roomStatus: upper(expected.roomStatus),
      cleaningStatus: upper(expected.cleaningStatus),
      cleaningType: upper(expected.cleaningType || NOVA.CLEANING_TYPES.NORMAL),
      assignmentType: upper(expected.assignmentType || NOVA.ROOMMAID_ASSIGNMENT_TYPES.SOLO),
      roommaidEmployeeNo: String(expected.roommaidEmployeeNo || '').trim(),
      secondaryRoommaidEmployeeNo: String(expected.secondaryRoommaidEmployeeNo || '').trim(),
      qmEmployeeNo: String(expected.qmEmployeeNo || '').trim()
    };
    const keys = [
      'roomStatus', 'cleaningStatus', 'cleaningType', 'assignmentType',
      'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo'
    ];
    if (keys.every(key => actual[key] === expectedNormalized[key])) return;
  }

  assertExpectedVersion_(expectedVersion, actualVersion, `${roomNo}호 객실`);
}

"""
if 'function assertIndicatorCheckoutExpectedState_(' not in indicator:
    indicator = indicator.replace(checkout_marker, checkout_helper + checkout_marker, 1)
INDICATOR.write_text(indicator, encoding='utf-8')


# -----------------------------------------------------------------------------
# Validation: syntax + whitespace + repository release guard runs again in CI.
# -----------------------------------------------------------------------------
subprocess.run(['node', '--check', str(CLOUD)], cwd=ROOT, check=True)
for path in [QM, MOBILE, INDICATOR]:
    subprocess.run(['node', '--check', str(path)], cwd=ROOT, check=True)

start = client.find('<script>')
end = client.rfind('</script>')
if start < 0 or end <= start:
    fail('Client embedded script not found')
tmp = ROOT / '.tmp_client_concurrency_v57.js'
tmp.write_text(client[start + len('<script>'):end], encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(tmp)], cwd=ROOT, check=True)
finally:
    if tmp.exists():
        tmp.unlink()

subprocess.run(
    ['git', 'diff', '--check', '--', 'Client.html', 'cloudrun/index.js', '16_QmChecklist.js', '10_Mobile.js', '06_Indicator.js'],
    cwd=ROOT,
    check=True
)

print('CONCURRENCY_V57_OK')
print('Changed: Client.html, cloudrun/index.js, 16_QmChecklist.js, 10_Mobile.js, 06_Indicator.js')
print('Policy: PostgreSQL row lock + action-scoped state conflict detection')
print('QM: assignment/status semantic guard; unrelated Sheet version bumps ignored')
print('Legacy checkout: Sheet version domain preserved; unrelated same-room changes do not create false conflict')
print('Roommaid START/COMPLETE: server state/assignment guard remains authoritative')
print('Syntax: PASS')
