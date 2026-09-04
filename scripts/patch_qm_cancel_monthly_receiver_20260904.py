from pathlib import Path

# 1) Server: QM-only assignment cancellation, preserve roommaid/completion state.
indicator = Path('06_Indicator.js')
text = indicator.read_text(encoding='utf-8')

old = """        case 'QM_WAITING':
          recordType = NOVA.RECORD_TYPES.QM;
          updates['청소상태'] = 'QM_WAITING';
          break;
        case 'CLEAR_ASSIGNMENT':
"""
new = """        case 'QM_WAITING':
          recordType = NOVA.RECORD_TYPES.QM;
          updates['청소상태'] = 'QM_WAITING';
          break;
        case 'QM_CLEAR': { // (QM 배정만 취소 · 룸메이드 배정/청소완료 실적 유지)
          recordType = NOVA.RECORD_TYPES.QM;
          const previousQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
          const previousCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
          if (!previousQmEmployeeNo) throw new Error('취소할 QM 배정이 없습니다.');
          if (previousCleaningStatus !== 'QM_WAITING') throw new Error('QM 점검 시작 전 배정만 취소할 수 있습니다.');
          targetEmployeeNo = previousQmEmployeeNo;
          updates['QM사번'] = '';
          updates['청소상태'] = 'COMPLETED';
          break;
        }
        case 'CLEAR_ASSIGNMENT':
"""
assert old in text, 'QM_WAITING server anchor not found'
text = text.replace(old, new, 1)

old = """          primaryEmployeeNo: updates['룸메이드사번'] || rowInfo.data['룸메이드사번'] || '',
          secondaryEmployeeNo: Object.prototype.hasOwnProperty.call(updates, '보조룸메이드사번') ? updates['보조룸메이드사번'] : (rowInfo.data['보조룸메이드사번'] || ''),
          creditUnit: getRoommaidCleaningCreditUnit_(updates['정비유형'] || rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
"""
new = """          primaryEmployeeNo: updates['룸메이드사번'] || rowInfo.data['룸메이드사번'] || '',
          secondaryEmployeeNo: Object.prototype.hasOwnProperty.call(updates, '보조룸메이드사번') ? updates['보조룸메이드사번'] : (rowInfo.data['보조룸메이드사번'] || ''),
          previousQmEmployeeNo: String(rowInfo.data['QM사번'] || '').trim(),
          qmEmployeeNo: Object.prototype.hasOwnProperty.call(updates, 'QM사번') ? String(updates['QM사번'] || '').trim() : String(rowInfo.data['QM사번'] || '').trim(),
          creditUnit: getRoommaidCleaningCreditUnit_(updates['정비유형'] || rowInfo.data['정비유형'] || NOVA.CLEANING_TYPES.NORMAL),
"""
assert old in text, 'history detail anchor not found'
text = text.replace(old, new, 1)

old = """    const finishedMs = Date.now();
    return {
      ok: true,
      version,
      room: responseRoom,
"""
new = """    let realtimeSyncPending = false;
    if (action === 'QM_CLEAR'
        && typeof novaRealtimeFinalEnabled_ === 'function'
        && novaRealtimeFinalEnabled_()
        && typeof syncNovaRealtimeRoomForAction === 'function') {
      try {
        syncNovaRealtimeRoomForAction(token, {
          businessDate,
          site: responseRoom.site,
          roomNo
        });
      } catch (syncError) {
        realtimeSyncPending = true;
        console.warn('[NOVA] QM 배정취소 후 Realtime 단건동기화 지연:', syncError);
      }
    }
    const finishedMs = Date.now();
    return {
      ok: true,
      version,
      room: responseRoom,
      realtimeSyncPending,
"""
assert old in text, 'response anchor not found'
text = text.replace(old, new, 1)
indicator.write_text(text, encoding='utf-8')

# 2) Monthly: when a QM history row has no assignee/processor/target, show registrant as receiver.
monthly = Path('11_Monthly.js')
text = monthly.read_text(encoding='utf-8')
old = """  const targetEmployeeNo = String(data['대상사번'] || '').trim();
  const assignedEmployeeNo = String(data['배정사번'] || '').trim();
  const processorEmployeeNo = String(data['처리자사번'] || '').trim();
  const employeeNos = Array.from(new Set([targetEmployeeNo, assignedEmployeeNo, processorEmployeeNo].filter(Boolean)));
  const primaryEmployeeNo = processorEmployeeNo || assignedEmployeeNo || targetEmployeeNo;
  const primaryUser = users[primaryEmployeeNo];
"""
new = """  const targetEmployeeNo = String(data['대상사번'] || '').trim();
  const assignedEmployeeNo = String(data['배정사번'] || '').trim();
  const processorEmployeeNo = String(data['처리자사번'] || '').trim();
  const registeredEmployeeNo = String(data['등록사번'] || detail.registeredBy || detail.registeredEmployeeNo || '').trim();
  const qmReceiverEmployeeNo = typeCode === 'QM' && !processorEmployeeNo && !assignedEmployeeNo && !targetEmployeeNo
    ? registeredEmployeeNo
    : '';
  const employeeNos = Array.from(new Set([targetEmployeeNo, assignedEmployeeNo, processorEmployeeNo, qmReceiverEmployeeNo].filter(Boolean)));
  const primaryEmployeeNo = processorEmployeeNo || assignedEmployeeNo || targetEmployeeNo || qmReceiverEmployeeNo;
  const primaryUser = users[primaryEmployeeNo];
"""
assert old in text, 'monthly employee fallback anchor not found'
text = text.replace(old, new, 1)
old = """    QM_ASSIGN: 'QM 배정', QM_WAITING: 'QM 대기', QM_START: 'QM 점검 시작',
    QM_COMPLETE: 'QM 완료', QM_REWORK: '재정비 요청'
"""
new = """    QM_ASSIGN: 'QM 배정', QM_WAITING: 'QM 대기', QM_CLEAR: 'QM 배정 취소', QM_START: 'QM 점검 시작',
    QM_COMPLETE: 'QM 완료', QM_REWORK: '재정비 요청'
"""
assert old in text, 'monthly QM status label anchor not found'
text = text.replace(old, new, 1)
monthly.write_text(text, encoding='utf-8')

# 3) Client: expose QM-only cancel before inspection starts and keep UI state aligned.
client = Path('Client.html')
text = client.read_text(encoding='utf-8')
old = """    const cleaningResetAvailable = cleaningCompletionLocked
      && Boolean(room.cleaningType || room.roommaidEmployeeNo || room.secondaryRoommaidEmployeeNo || room.qmEmployeeNo);
    const operationalStatus = normalizeIndicatorRoomOperationalStatus_(room.operationalStatus);
"""
new = """    const cleaningResetAvailable = cleaningCompletionLocked
      && Boolean(room.cleaningType || room.roommaidEmployeeNo || room.secondaryRoommaidEmployeeNo || room.qmEmployeeNo);
    const qmClearAvailable = Boolean(String(room.qmEmployeeNo || '').trim()) && cleaningStatusCode === 'QM_WAITING';
    const operationalStatus = normalizeIndicatorRoomOperationalStatus_(room.operationalStatus);
"""
assert old in text, 'client QM availability anchor not found'
text = text.replace(old, new, 1)

old = """            <button class=\"action-button\" type=\"button\" data-room-action=\"QM_ASSIGN\">QM배정</button>
            ${cleaningResetAvailable ? '<button class=\"action-button danger\" type=\"button\" data-room-action=\"CLEANING_RESET\">청소 초기화</button>' : ''}
"""
new = """            <button class=\"action-button\" type=\"button\" data-room-action=\"QM_ASSIGN\">QM배정</button>
            ${qmClearAvailable ? '<button class=\"action-button danger\" type=\"button\" data-room-action=\"QM_CLEAR\">QM배정 취소</button>' : ''}
            ${cleaningResetAvailable ? '<button class=\"action-button danger\" type=\"button\" data-room-action=\"CLEANING_RESET\">청소 초기화</button>' : ''}
"""
assert old in text, 'client QM button anchor not found'
text = text.replace(old, new, 1)

old = """    if (action === 'QM_ASSIGN') {
      const staff = state.indicator.data?.staff?.qms || [];
      const qm = staff.find(user => user.employeeNo === payload.employeeNo);
      return {
        qmEmployeeNo: payload.employeeNo || '',
        qmName: qm?.name || '',
        cleaningStatus: 'QM_WAITING'
      };
    }

    if (action === 'CLEAR_ASSIGNMENT') {
"""
new = """    if (action === 'QM_ASSIGN') {
      const staff = state.indicator.data?.staff?.qms || [];
      const qm = staff.find(user => user.employeeNo === payload.employeeNo);
      return {
        qmEmployeeNo: payload.employeeNo || '',
        qmName: qm?.name || '',
        cleaningStatus: 'QM_WAITING'
      };
    }

    if (action === 'QM_CLEAR') {
      return { qmEmployeeNo: '', qmName: '', cleaningStatus: 'COMPLETED' };
    }

    if (action === 'CLEAR_ASSIGNMENT') {
"""
assert old in text, 'client optimistic QM anchor not found'
text = text.replace(old, new, 1)

old = """      if (!confirmed) return;
    }
    const clickedAt = performance.now();
"""
new = """      if (!confirmed) return;
    }
    if (action === 'QM_CLEAR') {
      const confirmed = window.confirm(
        `${room.roomNo}호의 QM 배정을 취소합니다.\\n\\n`
        + '룸메이드 배정과 청소완료 실적은 유지되고, QM 배정만 해제됩니다.\\n'
        + 'QM 점검 시작 전 배정만 취소할 수 있습니다.\\n\\n'
        + '계속하시겠습니까?'
      );
      if (!confirmed) return;
    }
    const clickedAt = performance.now();
"""
# Only replace the first occurrence in runRoomAction block after CLEANING_RESET.
run_pos = text.index("async function runRoomAction")
anchor_pos = text.index(old, run_pos)
text = text[:anchor_pos] + text[anchor_pos:].replace(old, new, 1)

old = """      CLEANING_RESET: '청소 초기화',
      QM_ASSIGN: 'QM 배정',
      CLEAR_ASSIGNMENT: '배정 초기화',
"""
new = """      CLEANING_RESET: '청소 초기화',
      QM_ASSIGN: 'QM 배정',
      QM_CLEAR: 'QM 배정 취소',
      CLEAR_ASSIGNMENT: '배정 초기화',
"""
assert old in text, 'client action label anchor not found'
text = text.replace(old, new, 1)

old = """      if (action === 'CLEAR_ASSIGNMENT' || action === 'CLEANING_RESET') {
        Object.assign(resultRoom, emptyRoomAssignmentPatch_(), { cleaningStatus: 'WAITING' });
      }
      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
"""
new = """      if (action === 'CLEAR_ASSIGNMENT' || action === 'CLEANING_RESET') {
        Object.assign(resultRoom, emptyRoomAssignmentPatch_(), { cleaningStatus: 'WAITING' });
      }
      if (action === 'QM_CLEAR') {
        Object.assign(resultRoom, { qmEmployeeNo: '', qmName: '', cleaningStatus: 'COMPLETED' });
      }
      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
"""
assert old in text, 'client result merge anchor not found'
text = text.replace(old, new, 1)
client.write_text(text, encoding='utf-8')

print('QM cancel + monthly QM receiver fallback patch applied.')
