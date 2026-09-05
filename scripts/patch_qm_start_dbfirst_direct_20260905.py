from pathlib import Path
import sys

MARKER = 'QM_START_DB_FIRST_DIRECT_V1'
CLIENT_PATH = Path('Client.html')
INDEX_PATH = Path('Index.html')


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    sys.exit(81)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly 1 anchor, found {count}')
    return text.replace(old, new, 1)


def apply_client_patch():
    client = CLIENT_PATH.read_text(encoding='utf-8')
    if MARKER in client:
        print('QM direct start patch already applied to Client.html.')
        return

    start_anchor = "  async function startQmBrowseInspection_(roomNo, button) { // (QM 추가탭 체크리스트 즉시노출 v1)\n"
    helper = r'''  // QM_START_DB_FIRST_DIRECT_V1
  // 실제 Client IIFE 내부에서 실행되는 QM 추가조회 시작 경로입니다.
  // DB 상태확정은 Supabase RPC로 직접 처리하고 Sheet 이력 미러는 사용자 입력과 분리합니다.
  function novaQmSetStartPendingControls_(locked) {
    const modalRoot = $('modalRoot');
    if (!modalRoot) return;
    modalRoot.querySelectorAll(
      '.qm-checklist-modal [data-qm-photo-input], ' +
      '.qm-checklist-modal #qmInspectionSaveOnly, ' +
      '.qm-checklist-modal #qmChecklistSubmit, ' +
      '.qm-checklist-modal .qm-add-defect, ' +
      '.qm-checklist-modal [data-qm-photo-delete], ' +
      '.qm-checklist-modal [data-qm-remove-defect]'
    ).forEach(control => {
      control.disabled = Boolean(locked);
      if (locked) control.setAttribute('aria-disabled', 'true');
      else control.removeAttribute('aria-disabled');
    });
  }

  function novaQmMergePendingDraft_(serverDraft, localDraft) {
    const server = serverDraft || {};
    const local = localDraft || { answers: [], defects: [] };
    return Object.assign({}, server, local, {
      draftId: String(server.draftId || local.draftId || ''),
      rowNumber: Number(server.rowNumber || local.rowNumber || 0),
      businessDate: String(server.businessDate || local.businessDate || ''),
      site: String(server.site || local.site || ''),
      roomNo: String(server.roomNo || local.roomNo || ''),
      checklistRevision: String(server.checklistRevision || local.checklistRevision || ''),
      startedAt: String(server.startedAt || local.startedAt || ''),
      savedAt: String(server.savedAt || local.savedAt || ''),
      dbVersion: Number(server.dbVersion || local.dbVersion || 0)
    });
  }

  async function novaQmStartBrowseDbFirst_(room, view) {
    const normalizedView = String(view || '').trim().toUpperCase();
    if (!['CLEANED', 'VACANT'].includes(normalizedView)) return null;
    if (!novaRealtimeIsEnabled_() || novaRealtime_.qmDraftDbFirstEnabled !== true) return null;

    let auth;
    try {
      auth = await novaQmDraftAuthBundle_();
    } catch (error) {
      // 인증 토큰 조회까지만 실패한 경우 DB 변경은 전혀 없으므로 기존 경로 fallback이 안전합니다.
      console.warn('[NOVA QM] DB-first 시작 인증 준비 실패 · 기존 경로 사용:', error?.message || error);
      return null;
    }
    if (!auth?.token || !auth?.supabaseUrl || !auth?.publishableKey) return null;

    const requestId = novaRealtimeRequestId_('QM_BEGIN_DB_FIRST', room?.roomNo || '');
    const body = {
      p_business_date: String(state.mobile.businessDate || state.bootstrap.app.businessDate || ''),
      p_site: String(room?.site || state.mobile.site || ''),
      p_room_no: String(room?.roomNo || ''),
      p_view: normalizedView,
      p_request_id: requestId
    };
    const startedAt = performance.now();

    const send = async attempt => {
      const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_qm_begin_inspection_v1`;
      let response;
      try {
        response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'apikey': String(auth.publishableKey || ''),
            'Authorization': `Bearer ${String(auth.token || '')}`
          },
          body: JSON.stringify(body)
        });
      } catch (networkError) {
        // 요청 전송 뒤 결과만 유실됐을 수 있으므로 같은 requestId로만 재확인합니다.
        // 이 지점에서는 legacy 시작을 병행하지 않습니다.
        if (attempt < 2) {
          await novaRealtimeSleep_([140, 360, 800][attempt] || 800);
          return send(attempt + 1);
        }
        const error = new Error('QM 점검 시작 결과를 확인하지 못했습니다. 현재 객실상태를 다시 확인해 주세요.');
        error.code = 'QM_DB_RESULT_UNKNOWN';
        throw error;
      }

      let data = {};
      try { data = await response.json(); } catch (ignore) {}
      if (response.ok && data?.ok) return data;

      const code = String(data?.code || '').trim().toUpperCase();
      if (response.status === 401 && attempt < 2) {
        novaRealtime_.qmDraftAuthBundle = null;
        try { auth = await novaQmDraftAuthBundle_(); }
        catch (authError) {
          const error = new Error(authError?.message || 'QM DB 인증을 갱신하지 못했습니다.');
          error.code = 'QM_DB_AUTH_REFRESH_FAILED';
          throw error;
        }
        await novaRealtimeSleep_(160);
        return send(attempt + 1);
      }
      if ((response.status === 429 || response.status >= 500) && attempt < 2) {
        await novaRealtimeSleep_([140, 360, 800][attempt] || 800);
        return send(attempt + 1);
      }
      if (response.status === 404 || ['PGRST202', 'PGRST205'].includes(code)) {
        return { ok: false, legacyFallback: true, missingRpc: true };
      }

      const error = new Error(data?.message || data?.details || data?.hint || `QM DB 처리 오류 (${response.status})`);
      error.status = response.status;
      error.code = data?.code || '';
      throw error;
    };

    const result = await send(0);
    if (result?.legacyFallback) return result;
    if (result?.alreadyChecking === true && !result?.draft?.draftId) {
      // DB 전환 전부터 점검중인 기존 세션은 기존 Sheet 초안을 그대로 이어갑니다.
      return { ok: false, legacyFallback: true, existingSession: true };
    }
    if (!result?.draft?.draftId) throw new Error('QM 점검 초안을 준비하지 못했습니다.');

    return {
      ok: true,
      realtime: true,
      dbFirst: true,
      version: Number(result.version || result.room?.version || 0),
      room: Object.assign({}, result.room || {}, {
        rowNumber: Number(room?.rowNumber || 0),
        businessDate: String(state.mobile.businessDate || result.room?.businessDate || ''),
        site: String(result.room?.site || room?.site || state.mobile.site || ''),
        roomNo: String(result.room?.roomNo || room?.roomNo || ''),
        cleaningStatus: 'QM_CHECKING'
      }),
      draft: Object.assign({ answers: [], defects: [] }, result.draft || {}),
      checklist: null,
      requestId,
      alreadyChecking: Boolean(result.alreadyChecking),
      timing: { qmDbFirstClientMs: Math.round(performance.now() - startedAt) }
    };
  }

  function novaQmEnsureDbFirstMirror_(active) {
    if (!active?.dbFirst || !active?.draft?.draftId) return Promise.resolve(null);
    if (active.sheetMirrorReady) return Promise.resolve(active.sheetMirrorResult || null);
    if (active.sheetMirrorPromise) return active.sheetMirrorPromise;

    const task = (async () => {
      const delays = [0, 350, 900, 2200];
      let lastError = null;
      for (const delay of delays) {
        if (delay) await novaRealtimeSleep_(delay);
        try {
          const result = await callServer('ensureQmDbFirstDraftSheetMirror', state.token, {
            businessDate: active.draft.businessDate || state.mobile.businessDate,
            site: active.draft.site || state.mobile.site,
            roomNo: active.roomNo,
            rowNumber: Number(active.draft.rowNumber || 0),
            draftId: active.draft.draftId,
            draft: active.draft
          });
          if (result?.ok) {
            active.sheetMirrorReady = true;
            active.sheetMirrorResult = result;
            active.sheetExpectedVersion = Number(result.room?.sheetVersion || active.sheetExpectedVersion || 0);
            active.checklist = result.checklist || active.checklist;
            if (result.draft?.rowNumber) active.draft.rowNumber = Number(result.draft.rowNumber || 0);
            return result;
          }
          lastError = new Error(result?.message || 'QM 기존 이력 동기화 실패');
        } catch (error) {
          lastError = error;
        }
      }
      throw lastError || new Error('QM 기존 이력 동기화를 완료하지 못했습니다.');
    })();

    const tracked = task.finally(() => {
      if (active.sheetMirrorPromise === tracked) active.sheetMirrorPromise = null;
    });
    active.sheetMirrorPromise = tracked;
    return tracked;
  }

'''
    client = replace_once(client, start_anchor, helper + start_anchor, 'insert direct helper')

    old_pending_block = """    // 서버 왕복 전에 체크리스트 자체를 먼저 보여줍니다.\n    // 객실 확보가 확정되기 전에는 입력만 잠가 동시점검 안전성을 유지합니다.\n"""
    new_pending_block = """    // 서버 왕복 전에 체크리스트를 먼저 보여주고 결과선택·메모 입력은 즉시 허용합니다.\n    // 사진·저장·완료처럼 서버 확정이 필요한 작업만 시작확정/이력미러 완료 전까지 잠급니다.\n"""
    client = replace_once(client, old_pending_block, new_pending_block, 'pending comment')

    old_lock = """    const modalRoot = $('modalRoot');\n    if (modalRoot) {\n      modalRoot.querySelectorAll('.qm-checklist-modal .modal-body input, .qm-checklist-modal .modal-body textarea, .qm-checklist-modal .modal-body select, .qm-checklist-modal .modal-body button')\n        .forEach(control => { control.disabled = true; });\n    }\n    const pendingStatus = $('qmDraftSaveStatus');\n    if (pendingStatus) pendingStatus.textContent = '점검 시작 확인 중…';\n"""
    new_lock = """    novaQmSetStartPendingControls_(true);\n    const pendingStatus = $('qmDraftSaveStatus');\n    if (pendingStatus) pendingStatus.textContent = '점검 시작 처리 중 · 체크는 바로 가능합니다.';\n"""
    client = replace_once(client, old_lock, new_lock, 'pending input lock')

    old_call = """      const result = await callServer('startQmMobileBrowseInspection', state.token, {\n        businessDate: state.mobile.businessDate || state.bootstrap.app.businessDate,\n        site: room.site || state.mobile.site,\n        roomNo: room.roomNo,\n        rowNumber: Number(room.rowNumber || 0),\n        view\n      });\n      if (!result?.ok) throw new Error(result?.message || 'QM 점검을 시작하지 못했습니다.');\n\n      const confirmedChecklist = result.checklist || checklist;\n"""
    new_call = """      const startPayload = {\n        businessDate: state.mobile.businessDate || state.bootstrap.app.businessDate,\n        site: room.site || state.mobile.site,\n        roomNo: room.roomNo,\n        rowNumber: Number(room.rowNumber || 0),\n        view\n      };\n      const directResult = await novaQmStartBrowseDbFirst_(room, view);\n      const result = directResult?.legacyFallback\n        ? await callServer('startQmMobileBrowseInspection', state.token, startPayload)\n        : (directResult || await callServer('startQmMobileBrowseInspection', state.token, startPayload));\n      if (!result?.ok) throw new Error(result?.message || 'QM 점검을 시작하지 못했습니다.');\n\n      // 확인 중 입력한 결과/메모를 서버 응답으로 덮어쓰지 않습니다.\n      const pendingDraft = collectQmInspectionForm_() || previewActive.draft;\n      const hadLocalInput = Boolean(previewActive.localDirty);\n      const confirmedChecklist = result.checklist || checklist;\n"""
    client = replace_once(client, old_call, new_call, 'direct start call')

    old_assign = """      Object.assign(previewActive, {\n        checklist: confirmedChecklist,\n        draft: result.draft || previewActive.draft,\n        roomVersion: Number(confirmed.version || result.version || 0),\n        sheetExpectedVersion: 0,\n        localDirty: false,\n        realtime: true,\n        startPending: false\n      });\n"""
    new_assign = """      Object.assign(previewActive, {\n        checklist: confirmedChecklist,\n        draft: hadLocalInput\n          ? novaQmMergePendingDraft_(result.draft || {}, pendingDraft)\n          : (result.draft || pendingDraft),\n        roomVersion: Number(confirmed.version || result.version || 0),\n        sheetExpectedVersion: 0,\n        localDirty: hadLocalInput,\n        realtime: true,\n        dbFirst: result.dbFirst === true,\n        sheetMirrorReady: result.dbFirst === true ? false : true,\n        sheetMirrorResult: null,\n        sheetMirrorPromise: null,\n        startPending: false\n      });\n"""
    client = replace_once(client, old_assign, new_assign, 'preserve pending input')

    old_reopen = """      // 사용자가 기다리는 동안 모달을 닫지 않았다면 확정된 체크리스트로 즉시 활성화합니다.\n      const modalStillOpen = Boolean($('modalRoot') && !$('modalRoot').classList.contains('hidden') && $('qmChecklistInspectionItems'));\n      if (state.qmChecklist.activeInspection === previewActive && modalStillOpen) {\n        openQmInspectionModal_();\n      }\n      setSyncStatus(`${confirmed.roomNo}호 QM 점검 시작`);\n"""
    new_reopen = """      // 모달이 열려 있으면 입력값을 보존한 확정상태로 다시 렌더합니다.\n      const modalStillOpen = Boolean($('modalRoot') && !$('modalRoot').classList.contains('hidden') && $('qmChecklistInspectionItems'));\n      if (state.qmChecklist.activeInspection === previewActive && modalStillOpen) {\n        openQmInspectionModal_();\n      }\n      const dbMs = Number(result?.timing?.qmDbFirstClientMs || 0);\n      setSyncStatus(`${confirmed.roomNo}호 QM 점검 시작${dbMs ? ` · DB ${dbMs}ms` : ''}`);\n"""
    client = replace_once(client, old_reopen, new_reopen, 'confirmed modal reopen')

    old_modal_bind = """    bindQmInspectionModalEvents_();\n  }\n\n  function renderQmInspectionItem_(item, answer, index) { // (장소별 체크리스트 한 항목)\n"""
    new_modal_bind = """    bindQmInspectionModalEvents_();\n    if (active.startPending || (active.dbFirst && !active.sheetMirrorReady)) {\n      novaQmSetStartPendingControls_(true);\n      const status = $('qmDraftSaveStatus');\n      if (active.startPending) {\n        if (status) status.textContent = '점검 시작 처리 중 · 체크는 바로 가능합니다.';\n      } else if (active.dbFirst) {\n        if (status) status.textContent = active.localDirty\n          ? '점검 시작 완료 · 입력 보관 중 · 저장 준비 중…'\n          : '점검 시작 완료 · 저장 준비 중…';\n        void novaQmEnsureDbFirstMirror_(active).then(() => {\n          if (state.qmChecklist.activeInspection !== active) return;\n          novaQmSetStartPendingControls_(false);\n          const readyStatus = $('qmDraftSaveStatus');\n          if (readyStatus) readyStatus.textContent = active.localDirty ? '저장 준비 완료 · 변경사항 저장 대기…' : '저장 준비 완료';\n          if (active.localDirty) scheduleQmInspectionAutosave_();\n        }).catch(error => {\n          console.error('[NOVA QM] DB-first 기존 이력 미러 실패:', error);\n          if (state.qmChecklist.activeInspection !== active) return;\n          const failedStatus = $('qmDraftSaveStatus');\n          if (failedStatus) failedStatus.textContent = `저장 준비 오류 · ${error?.message || '재시도 필요'}`;\n          showToast('점검 시작은 완료됐지만 저장 준비를 확인해야 합니다. 체크 입력은 보관됩니다.');\n        });\n      }\n    }\n  }\n\n  function renderQmInspectionItem_(item, answer, index) { // (장소별 체크리스트 한 항목)\n"""
    client = replace_once(client, old_modal_bind, new_modal_bind, 'modal mirror readiness')

    old_autosave = """  function scheduleQmInspectionAutosave_() { // (입력 후 0.8초 자동저장)\n    const active = state.qmChecklist.activeInspection;\n    if (active) active.localDirty = true;\n    collectQmInspectionForm_();\n    const status = $('qmDraftSaveStatus');\n    if (status) status.textContent = '변경사항 저장 대기…';\n"""
    new_autosave = """  function scheduleQmInspectionAutosave_() { // (입력 후 0.8초 자동저장)\n    const active = state.qmChecklist.activeInspection;\n    if (active) active.localDirty = true;\n    collectQmInspectionForm_();\n    const status = $('qmDraftSaveStatus');\n    if (active?.startPending) {\n      if (status) status.textContent = '점검 시작 처리 중 · 입력 내용 임시 보관';\n      return;\n    }\n    if (status) status.textContent = '변경사항 저장 대기…';\n"""
    client = replace_once(client, old_autosave, new_autosave, 'pending autosave guard')

    old_persist = """      const persistDetail = async () => {\n        await ensureQmInspectionDraftReady_(active);\n        return submitQmInspectionDetailWithBusyRetry_({ // LIVE_OPERATION_RETRY_RESILIENCE_V1\n"""
    new_persist = """      const persistDetail = async () => {\n        await ensureQmInspectionDraftReady_(active);\n        if (active.dbFirst) await novaQmEnsureDbFirstMirror_(active);\n        return submitQmInspectionDetailWithBusyRetry_({ // LIVE_OPERATION_RETRY_RESILIENCE_V1\n"""
    client = replace_once(client, old_persist, new_persist, 'final detail mirror guard')

    CLIENT_PATH.write_text(client, encoding='utf-8')
    print('Applied QM_START_DB_FIRST_DIRECT_V1 to Client.html.')


def cleanup_dead_runtime_includes():
    index = INDEX_PATH.read_text(encoding='utf-8')
    old_lines = [
        "  <?!= include_('QmDbFirstClient'); ?> <!-- QM_BEGIN_DB_FIRST_V3 -->\n",
        "  <?!= include_('QmStartNonBlockingClient'); ?> <!-- QM_START_NONBLOCKING_V1 -->\n",
    ]
    changed = False
    for line in old_lines:
        if line in index:
            index = index.replace(line, '', 1)
            changed = True
    if changed:
        INDEX_PATH.write_text(index, encoding='utf-8')
        print('Removed ineffective external QM runtime wrappers from Index.html.')
    else:
        print('Ineffective external QM runtime wrappers already absent from Index.html.')


if __name__ == '__main__':
    apply_client_patch()
    cleanup_dead_runtime_includes()
