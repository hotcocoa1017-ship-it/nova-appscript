from pathlib import Path
import sys


def replace_required(text, old, new, label, count=1):
    if old not in text:
        if new in text:
            return text
        print(f'ERROR: {label} anchor not found.', file=sys.stderr)
        sys.exit(60)
    return text.replace(old, new, count)


def apply_qm_rework_operational_status_patch():
    marker = 'QM_REWORK_OPERATIONAL_STATUS_V1'

    # 1) 서버 공통 객실조치 상태에 REWORK 추가
    indicator_path = Path('06_Indicator.js')
    indicator = indicator_path.read_text(encoding='utf-8')
    if marker not in indicator:
        indicator = replace_required(
            indicator,
            "function normalizeIndicatorRoomOperationalStatus_(value) { // (고장·객실확인 상태 코드 정리)",
            "function normalizeIndicatorRoomOperationalStatus_(value) { // (고장·객실확인·재정비 상태 코드 정리 · QM_REWORK_OPERATIONAL_STATUS_V1)",
            'server operational-status normalizer marker'
        )
        indicator = replace_required(
            indicator,
            "  if (['ROOM_CHECK', 'ROOMCHECK', 'CHECK_ROOM', '객실확인'].includes(upper) || raw === '객실확인') return 'ROOM_CHECK';\n  return '';",
            "  if (['ROOM_CHECK', 'ROOMCHECK', 'CHECK_ROOM', '객실확인'].includes(upper) || raw === '객실확인') return 'ROOM_CHECK';\n  if (['REWORK', '재정비'].includes(upper) || raw === '재정비') return 'REWORK';\n  return '';",
            'server REWORK operational status'
        )
        indicator_path.write_text(indicator, encoding='utf-8')
        print('Applied REWORK operational status to 06_Indicator.js.')
    else:
        print('06_Indicator.js REWORK operational status already applied.')

    # 2) QM 즉시 재정비는 청소상태가 아니라 객실운영상태만 변경
    mobile_path = Path('10_Mobile.js')
    mobile = mobile_path.read_text(encoding='utf-8')
    if marker not in mobile:
        mobile = replace_required(
            mobile,
            "        updates['청소상태'] = 'REWORK';\n        updates.__reason = reason;",
            "        ensureIndicatorRoomOperationalStatusHeader_();\n        updates[indicatorRoomOperationalStatusHeader_()] = 'REWORK'; // QM_REWORK_OPERATIONAL_STATUS_V1\n        updates.__reason = reason;",
            'QM immediate rework state update'
        )
        mobile = replace_required(
            mobile,
            "        role,\n        reason,\n        beforeCleaningStatus: rowInfo.data['청소상태'],",
            "        role,\n        reason,\n        previousOperationalStatus: normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),\n        operationalStatus: role === 'QM' && action === 'REWORK'\n          ? 'REWORK'\n          : normalizeIndicatorRoomOperationalStatus_(rowInfo.data[indicatorRoomOperationalStatusHeader_()]),\n        beforeCleaningStatus: rowInfo.data['청소상태'],",
            'QM history operational status detail'
        )
        mobile = replace_required(
            mobile,
            "        cleaningStatus: updates['청소상태'],",
            "        cleaningStatus: updates['청소상태'] || rowInfo.data['청소상태'],",
            'QM history cleaning status preservation'
        )
        mobile = replace_required(
            mobile,
            "    checking: rooms.filter(room => room.cleaningStatus === 'QM_CHECKING').length,\n    rework: rooms.filter(room => room.cleaningStatus === 'REWORK').length,",
            "    checking: rooms.filter(room => room.cleaningStatus === 'QM_CHECKING' && room.operationalStatus !== 'REWORK').length,\n    rework: rooms.filter(room => room.operationalStatus === 'REWORK').length,",
            'QM summary operational rework'
        )
        mobile_path.write_text(mobile, encoding='utf-8')
        print('Applied QM immediate rework operational status to 10_Mobile.js.')
    else:
        print('10_Mobile.js REWORK operational status already applied.')

    # 3) 체크리스트 FAIL은 품질자료만 기록하고 청소상태는 항상 QM 완료
    checklist_path = Path('16_QmChecklist.js')
    checklist = checklist_path.read_text(encoding='utf-8')
    if marker not in checklist:
        checklist = replace_required(
            checklist,
            "    const targetCleaningStatus = passed ? 'QM_COMPLETED' : 'REWORK';",
            "    const targetCleaningStatus = 'QM_COMPLETED'; // QM_REWORK_OPERATIONAL_STATUS_V1 · FAIL은 품질자료만 기록",
            'checklist target cleaning status'
        )
        checklist = replace_required(
            checklist,
            "      result: passed ? 'PASS' : 'FAIL',\n      startedAt,",
            "      result: passed ? 'PASS' : 'FAIL',\n      qualityOnly: true,\n      reworkRequested: false,\n      startedAt,",
            'checklist quality-only marker'
        )
        checklist = replace_required(
            checklist,
            "      status: passed ? 'QM_COMPLETE' : 'QM_REWORK',",
            "      status: 'QM_COMPLETE',",
            'checklist QM history status'
        )
        checklist = replace_required(
            checklist,
            "        action: passed ? 'COMPLETE' : 'REWORK', role: 'QM', reason: failSummary,",
            "        action: 'COMPLETE', role: 'QM', qualityResult: passed ? 'PASS' : 'FAIL', reason: failSummary,",
            'checklist QM history action'
        )
        checklist = replace_required(
            checklist,
            "        sourceRoomStatus: passed ? String(rowInfo.data['객실상태'] || '').trim().toUpperCase() : '',",
            "        sourceRoomStatus: String(rowInfo.data['객실상태'] || '').trim().toUpperCase(),",
            'checklist source room status'
        )
        telegram_block = """
    if (!passed) {
      const usersByEmployeeNo = getUserIndex_().byEmployeeNo;
      [roommaidNo, secondaryRoommaidNo].filter(Boolean).forEach(employeeNo => {
        if (!usersByEmployeeNo[employeeNo]) return;
        queueRoommaidReworkTelegram_({
          businessDate, site: String(rowInfo.data['사업장'] || site).trim(), roomNo,
          targetUser: usersByEmployeeNo[employeeNo], reason: failSummary,
          preassigned: normalizeYesNo_(rowInfo.data['선배정여부']) === 'Y',
          vip: normalizeYesNo_(rowInfo.data['VIP여부']) === 'Y',
          importantRoom: normalizeYesNo_(rowInfo.data['중요객실여부']) === 'Y',
          registeredBy: user.employeeNo, version
        });
      });
    }
"""
        checklist = replace_required(
            checklist,
            telegram_block,
            "\n    // 체크리스트 FAIL은 품질자료 전용이며 룸메이드 재정비 알림을 생성하지 않습니다.\n",
            'checklist automatic rework telegram block'
        )
        checklist = replace_required(
            checklist,
            "      message: passed ? `QM 점검을 완료했습니다. (${durationMinutes == null ? '-' : durationMinutes}분)` : `하자 ${defects.length}건으로 재정비를 요청했습니다.`",
            "      message: passed ? `QM 점검을 완료했습니다. (${durationMinutes == null ? '-' : durationMinutes}분)` : `QM 점검을 완료했습니다. (불량 ${defects.length}건 기록 · ${durationMinutes == null ? '-' : durationMinutes}분)`",
            'checklist result message'
        )
        checklist_path.write_text(checklist, encoding='utf-8')
        print('Separated checklist defects from rework in 16_QmChecklist.js.')
    else:
        print('16_QmChecklist.js checklist/rework separation already applied.')

    # 4) 브라우저: 체크리스트는 항상 QM_COMPLETE, 즉시 재정비만 안전 Sheet 경로 사용
    client_path = Path('Client.html')
    client = client_path.read_text(encoding='utf-8')
    if marker not in client:
        client = replace_required(
            client,
            "    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)",
            "    if (mappedAction === 'QM_REWORK') { // QM_REWORK_OPERATIONAL_STATUS_V1 · Cloud Run 청소상태 REWORK 경로 우회\n      const directResult = await callServer(legacyMethod, state.token, legacySafe);\n      if (!directResult?.ok) throw new Error(directResult?.message || '재정비 상태를 저장하지 못했습니다.');\n      void callServer('syncNovaRealtimeRoomForAction', state.token, {\n        businessDate: safe.businessDate,\n        site: safe.site,\n        roomNo: safe.roomNo,\n        action: 'UPDATE_ROOM_OPERATION_STATUS'\n      }).catch(syncError => {\n        console.warn('[NOVA Realtime] 재정비 객실조치 DB 단건 동기화는 정기 동기화로 넘깁니다.', syncError);\n      });\n      return Object.assign({}, directResult, { reworkOperationalSafePath: true });\n    }\n\n    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)",
            'QM_REWORK safe path'
        )
        client = replace_required(
            client,
            "    const realtimeAction = passed ? 'QM_COMPLETE' : 'QM_REWORK';\n    const targetStatus = passed ? 'QM_COMPLETED' : 'REWORK';",
            "    const realtimeAction = 'QM_COMPLETE'; // QM_REWORK_OPERATIONAL_STATUS_V1 · FAIL은 품질자료만 기록\n    const targetStatus = 'QM_COMPLETED';",
            'checklist realtime completion action'
        )
        client = replace_required(
            client,
            "      showToast(passed ? 'QM 점검완료를 반영했습니다.' : `하자 ${(draft.defects || []).length + items.filter(item => answerMap[item.code]?.result === 'FAIL').length}건 · 재정비를 반영했습니다.`);",
            "      showToast(passed ? 'QM 점검완료를 반영했습니다.' : `QM 점검완료 · 불량 ${(draft.defects || []).length + items.filter(item => answerMap[item.code]?.result === 'FAIL').length}건 기록`);",
            'checklist client result toast'
        )
        client = replace_required(
            client,
            "  function normalizeIndicatorRoomOperationalStatus_(value) { // (통합 인디게이터 고장·객실확인 코드 정리)",
            "  function normalizeIndicatorRoomOperationalStatus_(value) { // (통합 인디게이터 고장·객실확인·재정비 코드 정리)",
            'client operational normalizer comment'
        )
        client = replace_required(
            client,
            "    if (['ROOM_CHECK', 'ROOMCHECK', 'CHECK_ROOM', '객실확인'].includes(upper) || raw === '객실확인') return 'ROOM_CHECK';\n    return '';",
            "    if (['ROOM_CHECK', 'ROOMCHECK', 'CHECK_ROOM', '객실확인'].includes(upper) || raw === '객실확인') return 'ROOM_CHECK';\n    if (['REWORK', '재정비'].includes(upper) || raw === '재정비') return 'REWORK';\n    return '';",
            'client REWORK normalizer'
        )
        client = replace_required(
            client,
            "    if (code === 'ROOM_CHECK') return '객실확인';\n    return '';",
            "    if (code === 'ROOM_CHECK') return '객실확인';\n    if (code === 'REWORK') return '재정비';\n    return '';",
            'client REWORK label'
        )
        client = replace_required(
            client,
            "    return code === 'BROKEN' ? 'broken' : code === 'ROOM_CHECK' ? 'room-check' : '';",
            "    return code === 'BROKEN' ? 'broken' : code === 'ROOM_CHECK' ? 'room-check' : code === 'REWORK' ? 'room-check' : '';",
            'client REWORK class'
        )
        client = replace_required(
            client,
            "      { code: 'OPERATION_ROOM_CHECK', label: '객실확인' },\n      { code: 'OPERATION_BROKEN', label: '고장객실' }",
            "      { code: 'OPERATION_ROOM_CHECK', label: '객실확인' },\n      { code: 'OPERATION_BROKEN', label: '고장객실' },\n      { code: 'OPERATION_REWORK', label: '재정비' }",
            'indicator REWORK filter'
        )
        client = replace_required(
            client,
            "      OPERATION_ROOM_CHECK: 0,\n      OPERATION_BROKEN: 0",
            "      OPERATION_ROOM_CHECK: 0,\n      OPERATION_BROKEN: 0,\n      OPERATION_REWORK: 0",
            'indicator REWORK count seed'
        )
        client = replace_required(
            client,
            "      if (operationalStatusCode === 'BROKEN') counts.OPERATION_BROKEN += 1;",
            "      if (operationalStatusCode === 'BROKEN') counts.OPERATION_BROKEN += 1;\n      if (operationalStatusCode === 'REWORK') counts.OPERATION_REWORK += 1;",
            'indicator REWORK count'
        )
        client = replace_required(
            client,
            "    } else if (state.indicator.filter === 'OPERATION_BROKEN') {\n      if (operationalStatusCode !== 'BROKEN') return false;\n    } else if (state.indicator.filter !== 'ALL' && roomStatusCode !== state.indicator.filter) {",
            "    } else if (state.indicator.filter === 'OPERATION_BROKEN') {\n      if (operationalStatusCode !== 'BROKEN') return false;\n    } else if (state.indicator.filter === 'OPERATION_REWORK') {\n      if (operationalStatusCode !== 'REWORK') return false;\n    } else if (state.indicator.filter !== 'ALL' && roomStatusCode !== state.indicator.filter) {",
            'indicator REWORK filter match'
        )
        badge_anchor = """    const operationBadges = [
      room.preassigned ? '<span class=\"mobile-operation-badge preassigned\">선배정</span>' : '',
      room.vip ? '<span class=\"mobile-operation-badge vip\">VIP</span>' : '',
      room.importantRoom ? '<span class=\"mobile-operation-badge important\">중요</span>' : ''
    ].filter(Boolean).join('');"""
        badge_replacement = """    const operationBadges = [
      room.preassigned ? '<span class=\"mobile-operation-badge preassigned\">선배정</span>' : '',
      room.vip ? '<span class=\"mobile-operation-badge vip\">VIP</span>' : '',
      room.importantRoom ? '<span class=\"mobile-operation-badge important\">중요</span>' : '',
      normalizeIndicatorRoomOperationalStatus_(room.operationalStatus) === 'REWORK' ? '<span class=\"mobile-operation-badge important\">재정비</span>' : ''
    ].filter(Boolean).join('');"""
        badge_count = client.count(badge_anchor)
        if badge_count < 1:
            print('ERROR: mobile operation badge anchor not found.', file=sys.stderr)
            sys.exit(61)
        client = client.replace(badge_anchor, badge_replacement)
        client = replace_required(
            client,
            "      if (room.cleaningStatus === 'QM_CHECKING') actions += `<button class=\"primary\" data-room-action=\"CONTINUE\" data-room-no=\"${escapeAttr(room.roomNo)}\">점검 계속</button><button data-room-action=\"REWORK\" data-room-no=\"${escapeAttr(room.roomNo)}\">즉시 재정비</button>`;",
            "      if (room.cleaningStatus === 'QM_CHECKING' && normalizeIndicatorRoomOperationalStatus_(room.operationalStatus) !== 'REWORK') actions += `<button class=\"primary\" data-room-action=\"CONTINUE\" data-room-no=\"${escapeAttr(room.roomNo)}\">점검 계속</button><button data-room-action=\"REWORK\" data-room-no=\"${escapeAttr(room.roomNo)}\">즉시 재정비</button>`;",
            'hide duplicate immediate rework button'
        )
        client_path.write_text(client, encoding='utf-8')
        print('Applied checklist/rework separation to Client.html.')
    else:
        print('Client.html checklist/rework separation already applied.')

    # 5) 새 품질전용 FAIL은 마감 중복검증의 신규 재정비 주기 경계로 보지 않음.
    #    과거 FAIL(마커 없음)은 기존 의미를 유지해 과거 데이터 해석을 바꾸지 않습니다.
    close_path = Path('19_RoommaidCloseJournal.js')
    close = close_path.read_text(encoding='utf-8')
    if marker not in close:
        close = replace_required(
            close,
            "  if (type === NOVA.RECORD_TYPES.QM_CHECKLIST && (status === 'FAIL' || action.includes('REWORK'))) return true;",
            "  if (type === NOVA.RECORD_TYPES.QM_CHECKLIST) { // QM_REWORK_OPERATIONAL_STATUS_V1\n    const detail = event.detail || {};\n    if (action.includes('REWORK')) return true;\n    if (status === 'FAIL' && detail.reworkRequested !== false && detail.qualityOnly !== true) return true;\n  }",
            'close journal checklist FAIL boundary'
        )
        close_path.write_text(close, encoding='utf-8')
        print('Separated quality-only FAIL from rework boundary in 19_RoommaidCloseJournal.js.')
    else:
        print('19_RoommaidCloseJournal.js checklist/rework boundary already applied.')


path = Path('Client.html')
text = path.read_text(encoding='utf-8')
marker = 'QM 추가탭 체크리스트 즉시노출 v1'

if marker in text:
    print('QM immediate checklist hotfix already applied.')
    apply_qm_rework_operational_status_patch()
    sys.exit(0)

start_anchor = "  async function startQmBrowseInspection_(roomNo, button) {"
end_anchor = "  async function handleMobileListClick(event) {"
start = text.find(start_anchor)
if start < 0:
    print('ERROR: QM browse inspection start function not found.', file=sys.stderr)
    sys.exit(40)
end = text.find(end_anchor, start)
if end < 0:
    print('ERROR: QM mobile click handler anchor not found.', file=sys.stderr)
    sys.exit(41)

replacement = r'''  async function startQmBrowseInspection_(roomNo, button) { // (QM 추가탭 체크리스트 즉시노출 v1)
    const view = qmMobileBrowseView_();
    const key = qmMobileBrowseKey_(view);
    const browse = state.mobile.qmBrowseData;
    const room = browse?.key === key && Array.isArray(browse.rooms)
      ? browse.rooms.find(item => String(item.roomNo || '') === String(roomNo || ''))
      : null;
    if (!room) {
      showToast('점검할 객실을 다시 불러와 주세요.');
      return;
    }

    const checklist = state.mobile.data?.qmChecklist || {};
    if (!(checklist.items || []).length && !(checklist.groups || []).length) {
      showToast('QM 체크리스트를 먼저 불러와 주세요.');
      return;
    }

    const originalText = button?.textContent || '';
    if (button) {
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = '시작 중…';
    }

    // 서버 왕복 전에 체크리스트 자체를 먼저 보여줍니다.
    // 객실 확보가 확정되기 전에는 입력만 잠가 동시점검 안전성을 유지합니다.
    const previewActive = {
      roomNo: String(room.roomNo || ''),
      checklist,
      draft: { answers: [], defects: [], startedAt: '', savedAt: '' },
      roomVersion: Number(room.version || 0),
      sheetExpectedVersion: 0,
      localDirty: false,
      realtime: true,
      initPromise: null,
      startPending: true
    };
    state.qmChecklist.activeInspection = previewActive;
    openQmInspectionModal_();
    const modalRoot = $('modalRoot');
    if (modalRoot) {
      modalRoot.querySelectorAll('.qm-checklist-modal .modal-body input, .qm-checklist-modal .modal-body textarea, .qm-checklist-modal .modal-body select, .qm-checklist-modal .modal-body button')
        .forEach(control => { control.disabled = true; });
    }
    const pendingStatus = $('qmDraftSaveStatus');
    if (pendingStatus) pendingStatus.textContent = '점검 시작 확인 중…';

    state.mobile.actionInFlight = Number(state.mobile.actionInFlight || 0) + 1;
    try {
      const result = await callServer('startQmMobileBrowseInspection', state.token, {
        businessDate: state.mobile.businessDate || state.bootstrap.app.businessDate,
        site: room.site || state.mobile.site,
        roomNo: room.roomNo,
        rowNumber: Number(room.rowNumber || 0),
        view
      });
      if (!result?.ok) throw new Error(result?.message || 'QM 점검을 시작하지 못했습니다.');

      const confirmedChecklist = result.checklist || checklist;
      if (!(confirmedChecklist.items || []).length && !(confirmedChecklist.groups || []).length) {
        throw new Error('QM 체크리스트를 불러오지 못했습니다.');
      }

      const confirmed = Object.assign({}, room, result.room || {}, {
        rowNumber: Number(result.room?.rowNumber || room.rowNumber || 0),
        businessDate: state.mobile.businessDate || room.businessDate,
        site: String(result.room?.site || room.site || state.mobile.site || ''),
        roomNo: String(room.roomNo || ''),
        qmEmployeeNo: String(state.bootstrap?.user?.employeeNo || ''),
        qmName: String(state.bootstrap?.user?.name || ''),
        cleaningStatus: 'QM_CHECKING',
        version: Number(result.room?.version || result.version || 0)
      });
      const targetRooms = state.mobile.data.rooms || (state.mobile.data.rooms = []);
      const existingIndex = targetRooms.findIndex(item => String(item.site || '') === confirmed.site && String(item.roomNo || '') === confirmed.roomNo);
      if (existingIndex >= 0) targetRooms[existingIndex] = Object.assign({}, targetRooms[existingIndex], confirmed);
      else targetRooms.push(confirmed);
      state.mobile.data.qmChecklist = confirmedChecklist;

      Object.assign(previewActive, {
        checklist: confirmedChecklist,
        draft: result.draft || previewActive.draft,
        roomVersion: Number(confirmed.version || result.version || 0),
        sheetExpectedVersion: 0,
        localDirty: false,
        realtime: true,
        startPending: false
      });

      // 시작 확정 후 기존 점검대상 흐름으로 복귀시켜 제출/재정비/완료를 그대로 사용합니다.
      state.mobile.qmView = 'TARGETS';
      state.mobile.qmBrowseData = null;
      state.mobile.qmBrowseBuilding = '';
      state.mobile.qmBrowseFloor = '';
      state.mobile.qmBrowseLimit = 50;
      renderQmBrowseTabs_();
      renderQmBrowseLocationFilters_();
      renderMobileSummary();
      renderMobileFilters();
      renderMobileList();

      // 사용자가 기다리는 동안 모달을 닫지 않았다면 확정된 체크리스트로 즉시 활성화합니다.
      const modalStillOpen = Boolean($('modalRoot') && !$('modalRoot').classList.contains('hidden') && $('qmChecklistInspectionItems'));
      if (state.qmChecklist.activeInspection === previewActive && modalStillOpen) {
        openQmInspectionModal_();
      }
      setSyncStatus(`${confirmed.roomNo}호 QM 점검 시작`);

      if (!previewActive.draft?.draftId) {
        void beginQmInspectionDraftInit_(previewActive).catch(error => {
          console.error('[NOVA QM] 추가탭 체크리스트 background 준비 실패:', error);
          if (state.qmChecklist.activeInspection === previewActive) {
            const status = $('qmDraftSaveStatus');
            if (status) status.textContent = `저장 준비 오류 · ${error?.message || ''}`;
            showToast('점검은 시작됐지만 체크리스트 저장준비가 지연되고 있습니다. 저장 시 자동 재시도합니다.');
          }
        });
      }
      void loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 추가탭 점검시작 후 화면갱신 실패:', error));
    } catch (error) {
      if (state.qmChecklist.activeInspection === previewActive) state.qmChecklist.activeInspection = null;
      const modalOpen = Boolean($('modalRoot') && !$('modalRoot').classList.contains('hidden'));
      if (modalOpen) closeModal();
      showToast(error?.message || 'QM 점검 시작 오류');
    } finally {
      state.mobile.actionInFlight = Math.max(0, Number(state.mobile.actionInFlight || 1) - 1);
      if (button && button.isConnected) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        button.textContent = originalText || '점검 시작';
      }
    }
  }

'''

updated = text[:start] + replacement + text[end:]
path.write_text(updated, encoding='utf-8')
print('Applied QM immediate checklist hotfix to Client.html.')
apply_qm_rework_operational_status_patch()
