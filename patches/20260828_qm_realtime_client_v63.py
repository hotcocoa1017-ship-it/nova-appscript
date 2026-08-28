from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'
QM = ROOT / '16_QmChecklist.js'
SYNC = ROOT / 'RealtimeDailySync.js'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


def replace_between(text, start_marker, end_marker, replacement, label):
    start = text.find(start_marker)
    if start < 0:
        fail(f'{label}: start marker not found')
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        fail(f'{label}: end marker not found')
    return text[:start] + replacement + text[end:]


# =============================================================================
# Client — QM 상태는 Cloud Run 즉시 확정, 체크리스트 상세이력은 background GAS.
# =============================================================================
client = CLIENT.read_text(encoding='utf-8')

# 1) Historical/transition protection: Sheet terminal QM status wins only when
#    its timestamp is newer than a stale DB waiting/checking status.
anchor = "  function novaRealtimeMergeRoom_(legacyRoom, realtimeRoom) {\n"
if client.count(anchor) != 1:
    fail('realtime merge anchor')
helper = r'''  function novaRealtimeUpdatedAtMs_(value) { // (Sheet/DB 수정시각 비교용)
    const text = String(value || '').trim();
    if (!text) return 0;
    const local = text.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2}):(\d{2})$/);
    const normalized = local
      ? `${local[1]}T${String(local[2]).padStart(2, '0')}:${local[3]}:${local[4]}+09:00`
      : text;
    const ms = Date.parse(normalized);
    return Number.isFinite(ms) ? ms : 0;
  }

'''
if 'function novaRealtimeUpdatedAtMs_' not in client:
    client = client.replace(anchor, helper + anchor, 1)

old = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;\n\n    // 일반 객실상태 Realtime 저장 직후 Sheet 미러가 따라올 때까지만 상태를 보호한다.\n"""
new = """    if (realtimeRoom.building) merged.building = realtimeRoom.building;\n\n    // QM을 Realtime으로 전환하기 전 생성된 과거행은 Sheet의 완료/재정비가 DB의\n    // QM대기/점검중보다 최신일 수 있다. 이 경우에만 최신 Sheet 상태를 보존한다.\n    const legacyCleaningStatus = String(legacyRoom?.cleaningStatus || '').trim().toUpperCase();\n    const realtimeCleaningStatus = String(realtimeRoom?.cleaningStatus || '').trim().toUpperCase();\n    const legacyQmTerminal = ['QM_COMPLETED', 'REWORK'].includes(legacyCleaningStatus);\n    const realtimeQmPreTerminal = ['QM_WAITING', 'QM_CHECKING'].includes(realtimeCleaningStatus);\n    if (legacyQmTerminal && realtimeQmPreTerminal) {\n      const sheetUpdatedMs = novaRealtimeUpdatedAtMs_(legacyRoom?.updatedAt);\n      const dbUpdatedMs = novaRealtimeUpdatedAtMs_(realtimeRoom?.updatedAt);\n      if (sheetUpdatedMs && (!dbUpdatedMs || sheetUpdatedMs >= dbUpdatedMs)) {\n        merged.cleaningStatus = legacyCleaningStatus;\n      }\n    }\n\n    // 일반 객실상태 Realtime 저장 직후 Sheet 미러가 따라올 때까지만 상태를 보호한다.\n"""
client = replace_once(client, old, new, 'stale QM DB terminal protection')

# 2) QM mobile also hydrates from DB and receives local broadcast repaint.
old = """    // 무료모드: ROOMMAID는 Realtime 상시 연결을 만들지 않습니다.\n    // 다만 현재 배정객실의 DB 상태를 화면 진입/30초 저빈도 조회로 hydrate 합니다.\n    if (state.activeMenu === 'cleaning' && role === 'ROOMMAID') {\n      const selected = String(state.mobile.site || '').trim();\n      if (selected) return [selected];\n      return [...new Set([\n        ...(state.mobile.data?.sites || []),\n        String(state.bootstrap.user?.defaultSite || '').trim()\n      ].map(String).map(v => v.trim()).filter(Boolean))];\n    }\n    return [];\n"""
new = """    // 직원 모바일은 상시 Realtime 채널을 만들지 않고 현재 화면 진입/저빈도 조회로 hydrate 합니다.\n    const mobileRealtimeRole = (state.activeMenu === 'cleaning' && role === 'ROOMMAID')\n      || (state.activeMenu === 'qm' && role === 'QM');\n    if (mobileRealtimeRole) {\n      const selected = String(state.mobile.site || '').trim();\n      if (selected) return [selected];\n      return [...new Set([\n        ...(state.mobile.data?.sites || []),\n        String(state.bootstrap.user?.defaultSite || '').trim()\n      ].map(String).map(v => v.trim()).filter(Boolean))];\n    }\n    return [];\n"""
client = replace_once(client, old, new, 'QM mobile relevant realtime sites')

old = """    if (state.activeMenu === 'cleaning' && role === 'ROOMMAID' && state.mobile.data) {\n      const sites = novaRealtimeRelevantSites_();\n      const lists = await Promise.all(sites.map(site =>\n        novaRealtimeLoadRoomsForSite_(state.mobile.businessDate || state.bootstrap.app.businessDate, site)\n          .catch(error => { console.error('[NOVA Realtime] 모바일 객실 조회 실패', site, error); return []; })\n      ));\n      const realtimeMap = new Map(lists.flat().map(room => [`${room.site}|${room.roomNo}`, room]));\n      state.mobile.data.rooms = (state.mobile.data.rooms || []).map(room =>\n        novaRealtimeMergeRoom_(room, realtimeMap.get(`${room.site}|${room.roomNo}`))\n      );\n      renderMobileData();\n    }\n"""
new = """    const mobileRealtimeRole = (state.activeMenu === 'cleaning' && role === 'ROOMMAID')\n      || (state.activeMenu === 'qm' && role === 'QM');\n    if (mobileRealtimeRole && state.mobile.data) {\n      const sites = novaRealtimeRelevantSites_();\n      const lists = await Promise.all(sites.map(site =>\n        novaRealtimeLoadRoomsForSite_(state.mobile.businessDate || state.bootstrap.app.businessDate, site)\n          .catch(error => { console.error('[NOVA Realtime] 모바일 객실 조회 실패', site, error); return []; })\n      ));\n      const realtimeMap = new Map(lists.flat().map(room => [`${room.site}|${room.roomNo}`, room]));\n      state.mobile.data.rooms = (state.mobile.data.rooms || []).map(room =>\n        novaRealtimeMergeRoom_(room, realtimeMap.get(`${room.site}|${room.roomNo}`))\n      );\n      renderMobileData();\n    }\n"""
client = replace_once(client, old, new, 'QM mobile realtime hydrate')

old = """      if (state.activeMenu === 'cleaning' && state.mobile.data?.role === 'ROOMMAID') {\n        refreshRoommaidMobileSummaryLocal_();\n        renderMobileSummary();\n        renderMobileList();\n      }\n"""
new = """      if (state.activeMenu === 'cleaning' && state.mobile.data?.role === 'ROOMMAID') {\n        refreshRoommaidMobileSummaryLocal_();\n        renderMobileSummary();\n        renderMobileList();\n      } else if (state.activeMenu === 'qm' && state.mobile.data?.role === 'QM') {\n        renderMobileSummary();\n        renderMobileList();\n      }\n"""
client = replace_once(client, old, new, 'QM mobile broadcast repaint')

# 3) Generic realtime helper accepts the three QM state actions.
old = """    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)\n"""
new = """    const realtimeAction = ['CLEANING_START', 'CLEANING_COMPLETE', 'CLEANING_RESET', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'QM_START', 'QM_COMPLETE', 'QM_REWORK', 'UPDATE_ROOM_OPERATION_STATUS', 'UPDATE_OPERATION_FLAGS', 'CLEAR_ASSIGNMENT'].includes(mappedAction)\n"""
client = replace_once(client, old, new, 'client realtime QM action whitelist')

old = """    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : mappedAction === 'CLEAR_ASSIGNMENT' ? '배정을 초기화했습니다.' : mappedAction === 'CLEANING_RESET' ? '청소완료 실적 초기화를 저장했습니다.' : '청소완료 처리했습니다.');\n"""
new = """    result.message = result.message || (mappedAction === 'CLEANING_START' ? '청소를 시작했습니다.' : mappedAction === 'ASSIGN_ROOMMAID' ? '룸메이드 배정을 저장했습니다.' : mappedAction === 'QM_ASSIGN' ? 'QM 배정을 저장했습니다.' : mappedAction === 'QM_START' ? 'QM 점검을 시작했습니다.' : mappedAction === 'QM_COMPLETE' ? 'QM 점검을 완료했습니다.' : mappedAction === 'QM_REWORK' ? '재정비를 요청했습니다.' : mappedAction === 'CHANGE_ROOM_STATUS' ? '객실상태를 저장했습니다.' : mappedAction === 'UPDATE_ROOM_OPERATION_STATUS' ? '객실 조치상태를 저장했습니다.' : mappedAction === 'UPDATE_OPERATION_FLAGS' ? '운영표시를 저장했습니다.' : mappedAction === 'CLEAR_ASSIGNMENT' ? '배정을 초기화했습니다.' : mappedAction === 'CLEANING_RESET' ? '청소완료 실적 초기화를 저장했습니다.' : '청소완료 처리했습니다.');\n"""
client = replace_once(client, old, new, 'client realtime QM action messages')

# 4) Replace QM start with Realtime-first + background draft initialization.
start_marker = "  async function startQmInspection_(roomNo, button) { // (점검 시작 즉시 장소별 체크리스트 팝업)\n"
end_marker = "  function openQmChecklistModal_(roomNo, button) { // (진행중 점검 다시 열기 호환)\n"
new_start = r'''  function applyQmRealtimeRoomLocal_(roomNo, realtimeRoom) { // (QM Realtime 응답 즉시 모바일 반영)
    const rooms = state.mobile.data?.rooms || [];
    const index = rooms.findIndex(item => String(item.roomNo || '') === String(roomNo || ''));
    if (index < 0 || !realtimeRoom) return null;
    const mapped = novaRealtimeMapRow_(realtimeRoom);
    rooms[index] = novaRealtimeMergeRoom_(rooms[index], mapped);
    if (state.activeMenu === 'qm') {
      renderMobileSummary();
      renderMobileList();
    }
    return rooms[index];
  }

  function beginQmInspectionDraftInit_(active) { // (상태변경 후 체크리스트 초안은 background 준비)
    if (!active) return Promise.reject(new Error('점검정보가 없습니다.'));
    if (active.draft?.draftId) return Promise.resolve(active);
    if (active.initPromise) return active.initPromise;
    const payload = {
      businessDate: state.mobile.businessDate,
      site: state.mobile.site,
      roomNo: active.roomNo,
      expectedVersion: Number(active.sheetExpectedVersion || 0),
      realtimeStarted: true,
      realtimeVersion: Number(active.roomVersion || 0)
    };
    const promise = callServer('startQmInspection', state.token, payload).then(result => {
      if (!result?.ok) throw new Error(result?.message || '체크리스트 저장준비에 실패했습니다.');
      const serverDraft = result.draft || {};
      const currentDraft = active.draft || { answers: [], defects: [] };
      active.checklist = result.checklist || active.checklist;
      active.draft = active.localDirty
        ? Object.assign({}, serverDraft, currentDraft, {
            draftId: serverDraft.draftId,
            rowNumber: Number(serverDraft.rowNumber || 0),
            startedAt: serverDraft.startedAt || currentDraft.startedAt || '',
            savedAt: serverDraft.savedAt || currentDraft.savedAt || ''
          })
        : serverDraft;
      if (state.qmChecklist.activeInspection === active) {
        const modalOpen = Boolean(document.querySelector('.qm-checklist-modal'));
        if (modalOpen && !active.localDirty) openQmInspectionModal_();
        const status = $('qmDraftSaveStatus');
        if (status) status.textContent = active.localDirty ? '저장 준비 완료 · 변경사항 저장 대기…' : `저장 준비 완료 ${active.draft?.savedAt || ''}`;
        if (modalOpen && active.localDirty) scheduleQmInspectionAutosave_();
      }
      return active;
    });
    active.initPromise = promise.finally(() => {
      if (active.initPromise === promise) active.initPromise = null;
    });
    return active.initPromise;
  }

  async function ensureQmInspectionDraftReady_(active) { // (사진/저장 시 background 초안 준비 완료 보장)
    const target = active || state.qmChecklist.activeInspection;
    if (!target) throw new Error('진행 중인 점검이 없습니다.');
    if (!target.draft?.draftId) await beginQmInspectionDraftInit_(target);
    if (!target.draft?.draftId) throw new Error('체크리스트 저장준비가 완료되지 않았습니다. 다시 시도하세요.');
    return target;
  }

  async function startQmInspection_(roomNo, button) { // (QM Realtime 시작 후 체크리스트 즉시 노출)
    const local = state.qmChecklist.activeInspection;
    if (local?.roomNo === roomNo) {
      openQmInspectionModal_();
      return;
    }
    if (button) button.disabled = true;
    try {
      const room = (state.mobile.data?.rooms || []).find(item => String(item.roomNo || '') === String(roomNo || ''));
      if (!room) throw new Error('점검할 객실을 찾을 수 없습니다.');

      if (!novaRealtime_.configLoaded) await initNovaRealtime_();
      if (!novaRealtimeIsEnabled_()) {
        const result = await callServer('startQmInspection', state.token, {
          businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo,
          expectedVersion: Number(room?.__sheetVersion || room?.version || 0)
        });
        if (!result?.ok) throw new Error(result?.message || '점검을 시작하지 못했습니다.');
        state.mobile.version = Number(result.version || state.mobile.version);
        state.mobile.data.qmChecklist = result.checklist || state.mobile.data.qmChecklist;
        state.qmChecklist.activeInspection = { roomNo, checklist: result.checklist, draft: result.draft, roomVersion: Number(result.room?.version || result.version || 0), localDirty: false };
        openQmInspectionModal_();
        loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 시작 후 화면갱신 실패:', error));
        return;
      }

      const realtime = await saveRoomActionRealtimeOrLegacy_('updateMobileRoomOperation', {
        businessDate: state.mobile.businessDate,
        site: state.mobile.site,
        roomNo,
        action: 'QM_START',
        expectedVersion: Number(room?.version || 0),
        expectedState: {
          cleaningStatus: String(room?.cleaningStatus || ''),
          qmEmployeeNo: String(room?.qmEmployeeNo || '')
        }
      });
      const localRoom = applyQmRealtimeRoomLocal_(roomNo, realtime.room) || room;
      const checklist = state.mobile.data?.qmChecklist || {};
      if (!(checklist.items || []).length) {
        throw new Error('QM 체크리스트를 불러오지 못했습니다. 화면을 새로고침한 뒤 다시 시도하세요.');
      }
      const active = {
        roomNo,
        checklist,
        draft: { answers: [], defects: [], startedAt: '', savedAt: '' },
        roomVersion: Number(realtime.version || realtime.room?.version || localRoom?.version || 0),
        sheetExpectedVersion: Number(room?.__sheetVersion || 0),
        localDirty: false,
        realtime: true,
        initPromise: null
      };
      state.qmChecklist.activeInspection = active;
      openQmInspectionModal_();
      if (button) button.disabled = false;
      void beginQmInspectionDraftInit_(active).catch(error => {
        console.error('[NOVA QM] 체크리스트 background 준비 실패:', error);
        if (state.qmChecklist.activeInspection === active) {
          const status = $('qmDraftSaveStatus');
          if (status) status.textContent = `저장 준비 오류 · ${error?.message || ''}`;
          showToast('점검은 시작됐지만 체크리스트 저장준비가 지연되고 있습니다. 저장 시 자동 재시도합니다.');
        }
      });
    } catch (error) {
      showToast(error?.message || '점검 시작 오류');
      if (button) button.disabled = false;
    }
  }

'''
client = replace_between(client, start_marker, end_marker, new_start, 'QM realtime start flow')

# Mark local edits and allow autosave to wait for background initialization.
old = """  function scheduleQmInspectionAutosave_() { // (입력 후 0.8초 자동저장)\n    collectQmInspectionForm_();\n"""
new = """  function scheduleQmInspectionAutosave_() { // (입력 후 0.8초 자동저장)\n    const active = state.qmChecklist.activeInspection;\n    if (active) active.localDirty = true;\n    collectQmInspectionForm_();\n"""
client = replace_once(client, old, new, 'QM local dirty tracking')

old = """  async function saveQmInspectionDraftNow_(showMessage) { // (점검 초안 서버 저장)\n    const active = state.qmChecklist.activeInspection;\n    if (!active?.draft?.draftId) return null;\n"""
new = """  async function saveQmInspectionDraftNow_(showMessage) { // (점검 초안 서버 저장)\n    const active = state.qmChecklist.activeInspection;\n    if (!active) return null;\n    if (!active?.draft?.draftId) {\n      const status = $('qmDraftSaveStatus');\n      if (status) status.textContent = '저장 준비 중…';\n      try { await ensureQmInspectionDraftReady_(active); }\n      catch (error) { if (status) status.textContent = `저장 준비 오류 · ${error?.message || ''}`; if (showMessage) showToast(error?.message || '임시 저장 준비 오류'); return null; }\n    }\n"""
client = replace_once(client, old, new, 'QM autosave waits for draft init')

# 5) Replace final submit: validate locally, Cloud Run state first, close immediately,
#    then persist the heavy detailed checklist in background.
final_start = "  async function submitQmInspectionFinal_(event) { // (QM 최종완료·재정비 저장)\n"
final_end = "\n\n  function renderMobileShell(menuId) { // (직원 스마트폰 전용 화면 골격)\n"
new_final = r'''  async function submitQmInspectionFinal_(event) { // (QM Realtime 최종상태 즉시반영·상세이력 background 저장)
    const button = event.currentTarget;
    button.disabled = true;
    const active = state.qmChecklist.activeInspection;
    if (!active) { button.disabled = false; return; }
    const draft = collectQmInspectionForm_();
    const items = active.checklist?.items || [];
    const answerMap = {};
    (draft.answers || []).forEach(answer => { answerMap[answer.code] = answer; });
    const missing = items.find(item => !answerMap[item.code]?.result);
    if (missing) { showToast(`${missing.placeLabel} · ${missing.label} 점검결과를 선택하세요.`); button.disabled = false; return; }
    const failNoNote = items.find(item => answerMap[item.code]?.result === 'FAIL' && !answerMap[item.code]?.note);
    if (failNoNote) { showToast(`${failNoNote.placeLabel} 불량 내용을 입력하세요.`); button.disabled = false; return; }
    const photoMissing = items.find(item => item.photoRequired && !(answerMap[item.code]?.photos || []).length);
    if (photoMissing) { showToast(`${photoMissing.placeLabel} · ${photoMissing.label} 항목의 사진을 등록하세요.`); button.disabled = false; return; }
    const invalidDefect = (draft.defects || []).find(defect => !defect.note || !(defect.photos || []).length);
    if (invalidDefect) { showToast('추가 하자는 내용과 사진을 모두 등록하세요.'); button.disabled = false; return; }

    if (state.qmChecklist.autosaveTimer) window.clearTimeout(state.qmChecklist.autosaveTimer);
    state.qmChecklist.autosaveTimer = null;
    const passed = !items.some(item => answerMap[item.code]?.result === 'FAIL') && !(draft.defects || []).length;
    const realtimeAction = passed ? 'QM_COMPLETE' : 'QM_REWORK';
    const targetStatus = passed ? 'QM_COMPLETED' : 'REWORK';
    const requestId = novaRealtimeRequestId_(realtimeAction, active.roomNo);
    const room = (state.mobile.data?.rooms || []).find(item => String(item.roomNo || '') === String(active.roomNo || ''));

    try {
      if (!novaRealtime_.configLoaded) await initNovaRealtime_();
      if (!novaRealtimeIsEnabled_()) {
        await ensureQmInspectionDraftReady_(active);
        const result = await callServer('submitQmChecklistInspection', state.token, {
          businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo: active.roomNo,
          draftId: active.draft.draftId, draftRowNumber: Number(active.draft.rowNumber || 0), revision: active.checklist.revision,
          answers: draft.answers, defects: draft.defects, expectedVersion: Number(active.roomVersion || 0)
        });
        if (!result?.ok) throw new Error(result?.message || '점검결과를 저장하지 못했습니다.');
        state.qmChecklist.activeInspection = null;
        closeModal();
        showToast(result.message || '점검결과를 저장했습니다.');
        loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 완료 후 화면갱신 실패:', error));
        return;
      }

      const realtime = await saveRoomActionRealtimeOrLegacy_('updateMobileRoomOperation', {
        businessDate: state.mobile.businessDate,
        site: state.mobile.site,
        roomNo: active.roomNo,
        action: realtimeAction,
        requestId,
        expectedVersion: Number(active.roomVersion || room?.version || 0),
        expectedState: {
          cleaningStatus: String(room?.cleaningStatus || 'QM_CHECKING'),
          qmEmployeeNo: String(room?.qmEmployeeNo || state.bootstrap?.user?.employeeNo || '')
        }
      });
      applyQmRealtimeRoomLocal_(active.roomNo, realtime.room);
      active.roomVersion = Number(realtime.version || realtime.room?.version || active.roomVersion || 0);
      state.qmChecklist.activeInspection = null;
      closeModal();
      showToast(passed ? 'QM 점검완료를 반영했습니다.' : `하자 ${(draft.defects || []).length + items.filter(item => answerMap[item.code]?.result === 'FAIL').length}건 · 재정비를 반영했습니다.`);

      // 무거운 Sheet 체크리스트/품질이력 저장은 사용자 응답 경로 밖에서 이어서 처리한다.
      const persistDetail = async () => {
        await ensureQmInspectionDraftReady_(active);
        return callServer('submitQmChecklistInspection', state.token, {
          businessDate: state.mobile.businessDate,
          site: state.mobile.site,
          roomNo: active.roomNo,
          draftId: active.draft.draftId,
          draftRowNumber: Number(active.draft.rowNumber || 0),
          revision: active.checklist.revision,
          answers: draft.answers,
          defects: draft.defects,
          expectedVersion: Number(active.sheetExpectedVersion || 0),
          realtimeCommitted: true,
          realtimeTargetStatus: targetStatus,
          realtimeRequestId: requestId,
          realtimeVersion: Number(realtime.version || 0)
        });
      };
      void persistDetail().then(result => {
        if (!result?.ok) throw new Error(result?.message || 'QM 상세이력 저장 실패');
        loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 상세이력 저장 후 갱신 실패:', error));
      }).catch(error => {
        console.error('[NOVA QM] 상태 반영 후 상세이력 저장 실패:', error);
        showToast(`QM 상태는 반영됐지만 상세이력 저장을 확인해야 합니다. · ${error?.message || ''}`);
      });
    } catch (error) {
      showToast(error?.message || '체크리스트 저장 오류');
      button.disabled = false;
    }
  }
'''
client = replace_between(client, final_start, final_end, new_final + "\n", 'QM realtime final flow')

CLIENT.write_text(client, encoding='utf-8')


# =============================================================================
# Apps Script QM server — Realtime state already committed; keep detailed Sheet
# history/checklist, avoid duplicating the room-state transition on start/final.
# =============================================================================
qm = QM.read_text(encoding='utf-8')

start_sig = "function startQmInspection(token, payload) { // (QM 점검 시작·실시간 초안 생성)\n"
start_end = "function saveQmInspectionDraft(token, payload) { // (QM 점검 실시간 자동저장·최종제출과 충돌 방지)\n"
new_server_start = r'''function startQmInspection(token, payload) { // (QM 점검 시작·Realtime 상태확정 후 초안 준비)
  return measureResponse_('startQmInspection', () => {
    const user = requireRole_(token, ['QM']);
    const safe = payload || {};
    const realtimeStarted = safe.realtimeStarted === true;
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || user.defaultSite || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!roomNo) throw new Error('객실번호가 없습니다.');

    if (!realtimeStarted) {
      const preflightSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const preflightRowInfo = findCurrentRoomRow_(preflightSheet, businessDate, site, roomNo);
      if (preflightRowInfo
          && String(preflightRowInfo.data['QM사번'] || '').trim() !== user.employeeNo
          && typeof novaRealtimeFinalEnabled_ === 'function'
          && novaRealtimeFinalEnabled_()
          && typeof mirrorNovaRealtimeEventsToSheets_ === 'function') {
        try { mirrorNovaRealtimeEventsToSheets_(); }
        catch (syncError) { console.warn('[NOVA QM] 점검시작 전 Realtime 배정 미러 실패:', syncError); }
      }
    }

    const writeLock = acquireWriteLock_();
    try {
      const currentSheet = getRequiredSheet_(NOVA.SHEETS.CURRENT);
      const rowInfo = findCurrentRoomRow_(currentSheet, businessDate, site, roomNo);
      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      if (String(rowInfo.data['QM사번'] || '').trim() !== user.employeeNo) throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');
      const currentStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
      if (!['QM_WAITING', 'COMPLETED', 'QM_CHECKING'].includes(currentStatus)) throw new Error('QM 점검대기 또는 점검중 객실만 시작할 수 있습니다.');

      let version = realtimeStarted
        ? Number(safe.realtimeVersion || rowInfo.data['마지막변경버전'] || 0)
        : Number(rowInfo.data['마지막변경버전'] || getMobileSyncVersion_('QM', { businessDate, site }));
      if (!realtimeStarted && currentStatus !== 'QM_CHECKING') {
        version = reserveDataVersion_({ lockHeld: true });
        updateRowByHeaders_(currentSheet, rowInfo.rowNumber, {
          '청소상태': 'QM_CHECKING',
          '마지막변경버전': version,
          '수정일시': nowText_()
        });
        SpreadsheetApp.flush();
        publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });
        appendUnifiedHistory_({
          recordType: NOVA.RECORD_TYPES.QM,
          businessDate,
          site: String(rowInfo.data['사업장'] || site).trim(),
          roomNo,
          targetEmployeeNo: user.employeeNo,
          status: 'QM_START',
          registeredBy: user.employeeNo,
          startedAt: nowText_(),
          version,
          detail: {
            action: 'START', role: 'QM', beforeCleaningStatus: currentStatus,
            cleaningStatus: 'QM_CHECKING', primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
            secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim()
          }
        });
      }
      const checklist = realtimeStarted ? getQmChecklistForSubmit_() : getQmChecklistForMobile_();
      const draft = ensureQmInspectionDraft_(user, businessDate, String(rowInfo.data['사업장'] || site).trim(), roomNo, rowInfo.data, checklist);
      const refreshed = Object.assign({}, rowInfo.data, { '청소상태': 'QM_CHECKING', '마지막변경버전': version });
      return {
        ok: true,
        version,
        checklist,
        draft,
        room: realtimeStarted ? {
          businessDate,
          site: String(rowInfo.data['사업장'] || site).trim(),
          roomNo,
          roomStatus: String(rowInfo.data['객실상태'] || '').trim(),
          cleaningStatus: 'QM_CHECKING',
          roommaidEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
          secondaryRoommaidEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
          qmEmployeeNo: user.employeeNo,
          version
        } : currentRoomObject_(refreshed, rowInfo.rowNumber, {}, getUserIndex_().byEmployeeNo),
        message: currentStatus === 'QM_CHECKING' ? '진행 중인 점검을 불러왔습니다.' : 'QM 점검을 시작했습니다.'
      };
    } finally {
      writeLock.releaseLock();
    }
  });
}

'''
qm = replace_between(qm, start_sig, start_end, new_server_start, 'server realtime QM start')

# Final submit accepts Realtime-first race states.
submit_start = qm.find('function submitQmChecklistInspection(token, payload)')
submit_end = qm.find('\nfunction getQmInspectionAnalytics(', submit_start)
if submit_start < 0 or submit_end < 0:
    fail('server QM submit block not found')
submit = qm[submit_start:submit_end]

old = """    const qmNo = String(rowInfo.data['QM사번'] || '').trim();\n    if (qmNo !== user.employeeNo) throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');\n    if (String(rowInfo.data['청소상태'] || '').trim().toUpperCase() !== 'QM_CHECKING') throw new Error('점검중 상태의 객실에서만 체크리스트를 제출할 수 있습니다.');\n\n"""
new = """    const qmNo = String(rowInfo.data['QM사번'] || '').trim();\n    if (qmNo !== user.employeeNo) throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');\n    const sheetCleaningStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();\n    const realtimeCommitted = safe.realtimeCommitted === true;\n    const allowedSubmitStatuses = realtimeCommitted\n      ? ['QM_WAITING', 'COMPLETED', 'QM_CHECKING', 'QM_COMPLETED', 'REWORK']\n      : ['QM_CHECKING'];\n    if (!allowedSubmitStatuses.includes(sheetCleaningStatus)) throw new Error('점검중 상태의 객실에서만 체크리스트를 제출할 수 있습니다.');\n\n"""
submit = replace_once(submit, old, new, 'server realtime final race status')

old = """    const completedAt = nowText_();\n    const startedAt = String(priorDetail.startedAt || draftInfo.data['등록일시'] || completedAt).trim();\n    const durationMinutes = minutesBetween_(startedAt, completedAt);\n    const updates = { '청소상태': passed ? 'QM_COMPLETED' : 'REWORK', '수정일시': completedAt };\n    // QM 점검완료 시에도 원래 객실상태를 유지한다.\n    // 공실(VACANT_CLEAN)은 최초 객실현황 업로드에서 누락된 객실에만 적용한다.\n    const version = reserveDataVersion_({ lockHeld: true });\n    updates['마지막변경버전'] = version;\n    updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);\n    SpreadsheetApp.flush();\n    publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });\n\n"""
new = """    const completedAt = nowText_();\n    const startedAt = String(priorDetail.startedAt || draftInfo.data['등록일시'] || completedAt).trim();\n    const durationMinutes = minutesBetween_(startedAt, completedAt);\n    const targetCleaningStatus = passed ? 'QM_COMPLETED' : 'REWORK';\n    const updates = { '청소상태': targetCleaningStatus, '수정일시': completedAt };\n    // Realtime이 이미 같은 최종상태를 Sheet에 미러했다면 상태행을 다시 쓰지 않는다.\n    // 아직 미러 전이면 기존과 동일하게 Sheet도 즉시 최종상태로 맞춘다.\n    let version = Number(rowInfo.data['마지막변경버전'] || 0);\n    if (sheetCleaningStatus !== targetCleaningStatus) {\n      version = reserveDataVersion_({ lockHeld: true });\n      updates['마지막변경버전'] = version;\n      updateRowByHeaders_(sheet, rowInfo.rowNumber, updates);\n      SpreadsheetApp.flush();\n      publishDataVersion_(version, { domains: ['ROOM'], businessDate, site: String(rowInfo.data['사업장'] || site).trim(), lockHeld: true });\n    }\n\n"""
submit = replace_once(submit, old, new, 'server realtime final idempotent Sheet update')

old = """      assignmentType\n    });\n"""
new = """      assignmentType,\n      realtimeRequestId: String(safe.realtimeRequestId || '').trim(),\n      realtimeVersion: Number(safe.realtimeVersion || 0)\n    });\n"""
# This exact tail occurs more than once in file; scope to submit only.
submit = replace_once(submit, old, new, 'server final realtime audit detail')
qm = qm[:submit_start] + submit + qm[submit_end:]
QM.write_text(qm, encoding='utf-8')


# =============================================================================
# Realtime event mirror — QM actions update Sheet status, but final detailed
# history is left to 16_QmChecklist.js to avoid duplicate quality records.
# =============================================================================
sync = SYNC.read_text(encoding='utf-8')
change_pos = sync.find("      if (action === 'CHANGE_ROOM_STATUS')")
if change_pos < 0:
    fail('Realtime mirror CHANGE_ROOM_STATUS anchor not found')
generic_pos = sync.find("      roomUpdates.push({\n        rowNumber: rowInfo.rowNumber,\n        cleaningStatus: afterStatus,", change_pos)
if generic_pos < 0:
    fail('Realtime mirror generic cleaning branch not found')
qm_branch = r'''      if (['QM_START', 'QM_COMPLETE', 'QM_REWORK'].includes(action)) {
        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: afterStatus,
          version,
          updatedAt: nowText_()
        });
        rowInfo.data['청소상태'] = afterStatus;
        rowInfo.data['마지막변경버전'] = version;
        if (action === 'QM_START') {
          historyPayloads.push({
            recordType: NOVA.RECORD_TYPES.QM,
            businessDate: recordBusinessDate,
            site: String(rowInfo.data['사업장'] || site).trim(),
            roomNo,
            targetEmployeeNo: employeeNo,
            status: 'QM_START',
            registeredBy: employeeNo,
            startedAt: eventTime || nowText_(),
            version,
            detail: {
              requestId,
              realtime: true,
              action: 'START',
              role: 'QM',
              beforeCleaningStatus: beforeStatus,
              cleaningStatus: afterStatus,
              primaryEmployeeNo: String(rowInfo.data['룸메이드사번'] || '').trim(),
              secondaryEmployeeNo: String(rowInfo.data['보조룸메이드사번'] || '').trim(),
              qmEmployeeNo: employeeNo,
              dbRoomVersion,
              dbEventTime: eventTime || ''
            }
          });
        }
        alreadyApplied.add(requestId);
        mirrored += 1;
        continue;
      }

'''
sync = sync[:generic_pos] + qm_branch + sync[generic_pos:]
SYNC.write_text(sync, encoding='utf-8')


# =============================================================================
# Validation
# =============================================================================
subprocess.run(['node', '--check', str(QM)], cwd=ROOT, check=True)
subprocess.run(['node', '--check', str(SYNC)], cwd=ROOT, check=True)

client_text = CLIENT.read_text(encoding='utf-8')
script_start = client_text.find('<script>')
script_end = client_text.rfind('</script>')
if script_start < 0 or script_end <= script_start:
    fail('Client script block not found')
tmp = ROOT / '.tmp_qm_v63_client.js'
tmp.write_text(client_text[script_start + len('<script>'):script_end], encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(tmp)], cwd=ROOT, check=True)
finally:
    if tmp.exists():
        tmp.unlink()

checks = [
    ('Client.html', client_text, "action: 'QM_START'"),
    ('Client.html', client_text, "const realtimeAction = passed ? 'QM_COMPLETE' : 'QM_REWORK';"),
    ('Client.html', client_text, 'function novaRealtimeUpdatedAtMs_'),
    ('Client.html', client_text, 'realtimeCommitted: true'),
    ('16_QmChecklist.js', QM.read_text(encoding='utf-8'), 'const realtimeStarted = safe.realtimeStarted === true;'),
    ('16_QmChecklist.js', QM.read_text(encoding='utf-8'), "['QM_WAITING', 'COMPLETED', 'QM_CHECKING', 'QM_COMPLETED', 'REWORK']"),
    ('RealtimeDailySync.js', SYNC.read_text(encoding='utf-8'), "['QM_START', 'QM_COMPLETE', 'QM_REWORK'].includes(action)"),
]
for filename, body, needle in checks:
    if needle not in body:
        fail(f'{filename} missing guard: {needle}')

# Existing requested UI/content protections remain.
if "role === 'QM' ? (assignedNames || '-') : roomStatus" not in client_text:
    fail('QM cleaner-name display regression')
if '양호/불량을 선택하세요. 불량은 내용을 입력하고' not in client_text:
    fail('QM simplified checklist guide regression')

subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
print('QM_REALTIME_CLIENT_V63_OK')
print('Changed: Client.html, 16_QmChecklist.js, RealtimeDailySync.js only')
print('QM start: Cloud Run state first, checklist opens immediately after fast response, draft initializes in background')
print('QM final: Cloud Run final state first, modal closes immediately, detailed checklist persists in background')
print('Indicator: newer Sheet QM terminal state protects against pre-migration stale DB waiting/checking')
print('Realtime mirror: QM state events no longer misclassified as ROOMMAID_COMPLETE')
print('Syntax/scope: PASS')
