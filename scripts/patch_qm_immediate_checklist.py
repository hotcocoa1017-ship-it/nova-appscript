from pathlib import Path
import sys

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
marker = 'QM 추가탭 체크리스트 즉시노출 v1'

if marker in text:
    print('QM immediate checklist hotfix already applied.')
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
