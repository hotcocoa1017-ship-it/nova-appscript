from pathlib import Path
import sys

CLIENT = Path('Client.html')
INDICATOR = Path('06_Indicator.js')
MARKER = 'QM_CLEAR_REWORK_CONTROLS_V1'

client = CLIENT.read_text(encoding='utf-8')
indicator = INDICATOR.read_text(encoding='utf-8')
client_changed = False
indicator_changed = False

# 1) 관리자/오더테이커 객실작업 모달에서 QM 배정 초기화를 QM 배정이 있는 동안 항상 노출합니다.
old_qm_available = "    const qmClearAvailable = Boolean(String(room.qmEmployeeNo || '').trim()) && cleaningStatusCode === 'QM_WAITING';"
new_qm_available = "    const qmClearAvailable = Boolean(String(room.qmEmployeeNo || '').trim()); // QM_CLEAR_REWORK_CONTROLS_V1"
if old_qm_available in client:
    client = client.replace(old_qm_available, new_qm_available, 1)
    client_changed = True
elif new_qm_available not in client:
    print('ERROR: qmClearAvailable anchor not found.', file=sys.stderr)
    raise SystemExit(101)

# 2) 객실조치 상태에 재정비 버튼을 추가합니다. 고장/객실확인/완료 기존 동작은 그대로 둡니다.
old_operational_buttons = '''<div class="modal-field full room-operational-status-editor"><span>객실조치 상태</span><div class="room-operational-status-options"><button class="room-operational-status-button${operationalStatus === 'BROKEN' ? ' active' : ''}" type="button" data-room-action="UPDATE_ROOM_OPERATION_STATUS" data-room-operational-status="BROKEN">고장</button><button class="room-operational-status-button${operationalStatus === 'ROOM_CHECK' ? ' active' : ''}" type="button" data-room-action="UPDATE_ROOM_OPERATION_STATUS" data-room-operational-status="ROOM_CHECK">객실확인</button><button class="room-operational-status-button complete" type="button" data-room-action="UPDATE_ROOM_OPERATION_STATUS" data-room-operational-status=""${operationalStatus ? '' : ' disabled'}>완료</button></div></div>'''
new_operational_buttons = '''<div class="modal-field full room-operational-status-editor"><span>객실조치 상태</span><div class="room-operational-status-options"><button class="room-operational-status-button${operationalStatus === 'BROKEN' ? ' active' : ''}" type="button" data-room-action="UPDATE_ROOM_OPERATION_STATUS" data-room-operational-status="BROKEN">고장</button><button class="room-operational-status-button${operationalStatus === 'ROOM_CHECK' ? ' active' : ''}" type="button" data-room-action="UPDATE_ROOM_OPERATION_STATUS" data-room-operational-status="ROOM_CHECK">객실확인</button><button class="room-operational-status-button${operationalStatus === 'REWORK' ? ' active' : ''}" type="button" data-room-action="UPDATE_ROOM_OPERATION_STATUS" data-room-operational-status="REWORK">재정비</button><button class="room-operational-status-button complete" type="button" data-room-action="UPDATE_ROOM_OPERATION_STATUS" data-room-operational-status=""${operationalStatus ? '' : ' disabled'}>완료</button></div></div>'''
if old_operational_buttons in client:
    client = client.replace(old_operational_buttons, new_operational_buttons, 1)
    client_changed = True
elif new_operational_buttons not in client:
    print('ERROR: operational status buttons anchor not found.', file=sys.stderr)
    raise SystemExit(102)

# 3) 버튼/토스트 문구를 'QM배정 초기화'로 통일합니다.
client2 = client.replace(
    '${qmClearAvailable ? \'<button class="action-button danger" type="button" data-room-action="QM_CLEAR">QM배정 취소</button>\' : \'\'}',
    '${qmClearAvailable ? \'<button class="action-button danger" type="button" data-room-action="QM_CLEAR">QM배정 초기화</button>\' : \'\'}',
    1
)
if client2 != client:
    client = client2
    client_changed = True
elif 'data-room-action="QM_CLEAR">QM배정 초기화</button>' not in client:
    print('ERROR: QM clear button label anchor not found.', file=sys.stderr)
    raise SystemExit(103)

old_action_label = "      QM_CLEAR: 'QM 배정 취소',"
new_action_label = "      QM_CLEAR: 'QM 배정 초기화',"
if old_action_label in client:
    client = client.replace(old_action_label, new_action_label, 1)
    client_changed = True
elif new_action_label not in client:
    print('ERROR: QM clear action label anchor not found.', file=sys.stderr)
    raise SystemExit(104)

# 4) 초기화 확인문구는 줄바꿈 표현과 무관하게 핵심 문구만 교체합니다.
if 'QM 배정을 초기화합니다.' not in client:
    updated = client.replace('QM 배정을 취소합니다.', 'QM 배정을 초기화합니다.', 1)
    if updated == client:
        print('ERROR: QM clear confirm title anchor not found.', file=sys.stderr)
        raise SystemExit(105)
    client = updated
    client_changed = True
if '기존 체크리스트 초안·이력은 보존' not in client:
    updated = client.replace(
        'QM 점검 시작 전 배정만 취소할 수 있습니다.',
        '점검중인 경우 기존 체크리스트 초안·이력은 보존되며 해당 QM은 더 이상 완료할 수 없습니다.',
        1
    )
    if updated == client:
        print('ERROR: QM clear confirm detail anchor not found.', file=sys.stderr)
        raise SystemExit(106)
    client = updated
    client_changed = True

# 5) 수동 '재정비' 객실조치는 기존 고장/객실확인 Cloud Run 경로와 분리해
#    검증된 Apps Script 안전저장 -> 단건 DB 동기화로 처리합니다.
rework_direct_marker = 'QM_CLEAR_REWORK_CONTROLS_V1 · 관리자 재정비 객실조치 안전경로'
if rework_direct_marker not in client:
    anchor = "    const operationalStatusCompletionDirect = mappedAction === 'UPDATE_ROOM_OPERATION_STATUS'\n      && !String(safe.operationalStatus || '').trim();\n"
    if anchor not in client:
        print('ERROR: operational status direct anchor not found.', file=sys.stderr)
        raise SystemExit(107)
    block = '''    const operationalStatusReworkDirect = mappedAction === 'UPDATE_ROOM_OPERATION_STATUS'
      && String(safe.operationalStatus || '').trim().toUpperCase() === 'REWORK';
    if (operationalStatusReworkDirect) { // QM_CLEAR_REWORK_CONTROLS_V1 · 관리자 재정비 객실조치 안전경로
      const directPayload = Object.assign({}, legacySafe, {
        action: 'UPDATE_ROOM_OPERATION_STATUS',
        operationalStatus: 'REWORK',
        expectedVersion: 0,
        expectedOperationalStatus: String(safe?.expectedState?.operationalStatus || '')
      });
      delete directPayload.sheetExpectedVersion;
      const directResult = await callServer('updateRoomOperationalStatusSafe', state.token, directPayload);
      if (!directResult?.ok) throw new Error(directResult?.message || '재정비 객실조치를 저장하지 못했습니다.');
      void callServer('syncNovaRealtimeRoomForAction', state.token, {
        businessDate: safe.businessDate,
        site: safe.site,
        roomNo: safe.roomNo,
        action: 'UPDATE_ROOM_OPERATION_STATUS'
      }).catch(syncError => {
        console.warn('[NOVA Realtime] 관리자 재정비 객실조치 DB 단건 동기화는 정기 동기화로 넘깁니다.', syncError);
      });
      return Object.assign({}, directResult, { reworkOperationalSafePath: true });
    }

'''
    client = client.replace(anchor, block + anchor, 1)
    client_changed = True

old_operation_action_label = "      UPDATE_ROOM_OPERATION_STATUS: payload.operationalStatus === 'BROKEN' ? '고장 등록' : payload.operationalStatus === 'ROOM_CHECK' ? '객실확인 등록' : '객실조치 완료'"
new_operation_action_label = "      UPDATE_ROOM_OPERATION_STATUS: payload.operationalStatus === 'BROKEN' ? '고장 등록' : payload.operationalStatus === 'ROOM_CHECK' ? '객실확인 등록' : payload.operationalStatus === 'REWORK' ? '재정비 등록' : '객실조치 완료'"
if old_operation_action_label in client:
    client = client.replace(old_operation_action_label, new_operation_action_label, 1)
    client_changed = True
elif new_operation_action_label not in client:
    print('ERROR: operational action label anchor not found.', file=sys.stderr)
    raise SystemExit(108)

# 6) REWORK 공통 정규화는 앞선 QM immediate patch가 매 배포 먼저 보장합니다.
#    여기서는 실제 반영 여부를 확인해 후속 안전저장/DB동기화가 빈 값으로 바뀌지 않게 합니다.
if "return 'REWORK';" not in indicator:
    print('ERROR: server REWORK operational status normalizer is missing.', file=sys.stderr)
    raise SystemExit(109)

# 7) QM 초기화는 QM_WAITING뿐 아니라 점검중/완료 상태에서도 복구용으로 허용합니다.
old_qm_clear_server = '''        case 'QM_CLEAR': { // (QM 배정만 취소 · 룸메이드 배정/청소완료 실적 유지)
          recordType = NOVA.RECORD_TYPES.QM;
          const previousQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
          const previousCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
          if (!previousQmEmployeeNo) throw new Error('취소할 QM 배정이 없습니다.');
          if (previousCleaningStatus !== 'QM_WAITING') throw new Error('QM 점검 시작 전 배정만 취소할 수 있습니다.');
          targetEmployeeNo = previousQmEmployeeNo;
          updates['QM사번'] = '';
          updates['청소상태'] = 'COMPLETED';
          break;
        }'''
new_qm_clear_server = '''        case 'QM_CLEAR': { // (QM 배정 초기화 · 룸메이드 배정/청소완료 실적 및 기존 점검이력 유지) // QM_CLEAR_REWORK_CONTROLS_V1
          recordType = NOVA.RECORD_TYPES.QM;
          const previousQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
          const previousCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
          if (!previousQmEmployeeNo) throw new Error('초기화할 QM 배정이 없습니다.');
          targetEmployeeNo = previousQmEmployeeNo;
          updates['QM사번'] = '';
          if (['QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED', 'REWORK'].includes(previousCleaningStatus)) {
            updates['청소상태'] = 'COMPLETED';
          }
          break;
        }'''
if old_qm_clear_server in indicator:
    indicator = indicator.replace(old_qm_clear_server, new_qm_clear_server, 1)
    indicator_changed = True
elif new_qm_clear_server not in indicator:
    print('ERROR: server QM_CLEAR anchor not found.', file=sys.stderr)
    raise SystemExit(110)

# 최종 안전검증
required_client = [
    'QM_CLEAR_REWORK_CONTROLS_V1',
    'data-room-operational-status="REWORK">재정비</button>',
    'data-room-action="QM_CLEAR">QM배정 초기화</button>',
    "payload.operationalStatus === 'REWORK' ? '재정비 등록'",
    'operationalStatusReworkDirect',
    '기존 체크리스트 초안·이력은 보존'
]
for needle in required_client:
    if needle not in client:
        print(f'ERROR: client validation failed: {needle}', file=sys.stderr)
        raise SystemExit(111)

required_indicator = [
    "return 'REWORK';",
    "case 'QM_CLEAR': { // (QM 배정 초기화",
    "['QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED', 'REWORK'].includes(previousCleaningStatus)"
]
for needle in required_indicator:
    if needle not in indicator:
        print(f'ERROR: indicator validation failed: {needle}', file=sys.stderr)
        raise SystemExit(112)

if client_changed:
    CLIENT.write_text(client, encoding='utf-8')
if indicator_changed:
    INDICATOR.write_text(indicator, encoding='utf-8')

print(f'QM clear/rework controls patch ready. client_changed={client_changed}, indicator_changed={indicator_changed}')
