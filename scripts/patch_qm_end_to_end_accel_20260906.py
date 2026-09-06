from pathlib import Path
import sys

CLIENT = Path('Client.html')
MARKER = 'QM_END_TO_END_ACCEL_V1'


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(86)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly 1 anchor, found {count}')
    return text.replace(old, new, 1)


def main():
    text = CLIENT.read_text(encoding='utf-8')
    if MARKER in text:
        print('QM end-to-end acceleration patch already applied.')
        return
    if 'QM_START_DB_FIRST_DIRECT_V1' not in text:
        fail('QM_START_DB_FIRST_DIRECT_V1 must be applied first')

    # 1) The same atomic DB-first RPC already supports assigned TARGETS.
    text = replace_once(
        text,
        "    if (!['CLEANED', 'VACANT'].includes(normalizedView)) return null;",
        "    if (!['TARGETS', 'CLEANED', 'VACANT'].includes(normalizedView)) return null; // QM_END_TO_END_ACCEL_V1",
        'enable TARGETS in DB-first start'
    )

    old_start = r'''  async function startQmInspection_(roomNo, button) { // (QM Realtime 시작 후 체크리스트 즉시 노출)
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

    new_start = r'''  async function startQmInspection_(roomNo, button) { // (QM_END_TO_END_ACCEL_V1 · 전체 QM 시작경로 DB-first/즉시 체크리스트)
    const local = state.qmChecklist.activeInspection;
    if (local?.roomNo === roomNo) {
      openQmInspectionModal_();
      return;
    }

    const room = (state.mobile.data?.rooms || []).find(item => String(item.roomNo || '') === String(roomNo || ''));
    if (!room) return showToast('점검할 객실을 찾을 수 없습니다.');
    const checklist = state.mobile.data?.qmChecklist || {};
    if (!(checklist.items || []).length && !(checklist.groups || []).length) {
      return showToast('QM 체크리스트를 불러오지 못했습니다. 화면을 새로고침한 뒤 다시 시도하세요.');
    }

    const originalText = button?.textContent || '';
    if (button) {
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = '시작 중…';
    }

    // 네트워크 왕복보다 먼저 체크리스트를 열어 결과/메모 입력을 허용합니다.
    // 사진·저장·완료 등 서버 확정 작업만 시작 확정 전 잠급니다.
    const previewActive = {
      roomNo: String(roomNo || ''),
      checklist,
      draft: { answers: [], defects: [], startedAt: '', savedAt: '' },
      roomVersion: Number(room?.version || 0),
      sheetExpectedVersion: Number(room?.__sheetVersion || 0),
      localDirty: false,
      realtime: true,
      initPromise: null,
      startPending: true
    };
    state.qmChecklist.activeInspection = previewActive;
    openQmInspectionModal_();
    novaQmSetStartPendingControls_(true);
    const pendingStatus = $('qmDraftSaveStatus');
    if (pendingStatus) pendingStatus.textContent = '점검 시작 처리 중 · 체크는 바로 가능합니다.';

    try {
      if (!novaRealtime_.configLoaded) await initNovaRealtime_();
      let result = null;

      if (novaRealtimeIsEnabled_()) {
        // 신규 배정객실과 기존 DB-first 점검중 객실은 한 RPC에서 상태+초안을 함께 확정합니다.
        // 전환 전 QM_CHECKING인데 DB 초안이 없는 객실은 helper가 legacyFallback으로 보호합니다.
        const directResult = await novaQmStartBrowseDbFirst_(room, 'TARGETS');
        if (directResult && !directResult.legacyFallback) {
          result = directResult;
        } else {
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
          result = {
            ok: true,
            realtime: true,
            dbFirst: false,
            version: Number(realtime.version || realtime.room?.version || 0),
            room: realtime.room || null,
            checklist,
            draft: null
          };
        }
      } else {
        result = await callServer('startQmInspection', state.token, {
          businessDate: state.mobile.businessDate,
          site: state.mobile.site,
          roomNo,
          expectedVersion: Number(room?.__sheetVersion || room?.version || 0)
        });
      }

      if (!result?.ok) throw new Error(result?.message || '점검을 시작하지 못했습니다.');
      const pendingDraft = collectQmInspectionForm_() || previewActive.draft;
      const hadLocalInput = Boolean(previewActive.localDirty);
      const confirmedChecklist = result.checklist || checklist;
      if (!(confirmedChecklist.items || []).length && !(confirmedChecklist.groups || []).length) {
        throw new Error('QM 체크리스트를 불러오지 못했습니다.');
      }

      const confirmedRoom = Object.assign({}, room, result.room || {}, {
        roomNo: String(roomNo || ''),
        site: String(result.room?.site || room.site || state.mobile.site || ''),
        qmEmployeeNo: String(state.bootstrap?.user?.employeeNo || room.qmEmployeeNo || ''),
        qmName: String(state.bootstrap?.user?.name || room.qmName || ''),
        cleaningStatus: 'QM_CHECKING',
        version: Number(result.version || result.room?.version || room.version || 0)
      });
      applyQmRealtimeRoomLocal_(roomNo, confirmedRoom);
      state.mobile.data.qmChecklist = confirmedChecklist;

      Object.assign(previewActive, {
        checklist: confirmedChecklist,
        draft: result.draft?.draftId
          ? (hadLocalInput ? novaQmMergePendingDraft_(result.draft, pendingDraft) : result.draft)
          : pendingDraft,
        roomVersion: Number(confirmedRoom.version || 0),
        sheetExpectedVersion: result.dbFirst === true ? 0 : Number(room?.__sheetVersion || 0),
        localDirty: hadLocalInput,
        realtime: Boolean(novaRealtimeIsEnabled_()),
        dbFirst: result.dbFirst === true,
        sheetMirrorReady: result.dbFirst === true ? false : true,
        sheetMirrorResult: null,
        sheetMirrorPromise: null,
        startPending: false
      });

      const modalStillOpen = Boolean($('modalRoot') && !$('modalRoot').classList.contains('hidden') && $('qmChecklistInspectionItems'));
      if (state.qmChecklist.activeInspection === previewActive && modalStillOpen) openQmInspectionModal_();

      if (!previewActive.draft?.draftId) {
        void beginQmInspectionDraftInit_(previewActive).catch(error => {
          console.error('[NOVA QM] legacy 체크리스트 background 준비 실패:', error);
          if (state.qmChecklist.activeInspection === previewActive) {
            const status = $('qmDraftSaveStatus');
            if (status) status.textContent = `저장 준비 오류 · ${error?.message || ''}`;
            showToast('점검은 시작됐지만 저장 준비가 지연되고 있습니다. 저장 시 자동 재시도합니다.');
          }
        });
      } else if (previewActive.dbFirst) {
        // 기존 Sheet/품질이력 호환은 사용자 입력과 분리하여 후행합니다.
        void novaQmEnsureDbFirstMirror_(previewActive).catch(error => {
          console.warn('[NOVA QM] 점검시작 Sheet 이력 미러 지연:', error?.message || error);
        });
      }

      const dbMs = Number(result?.timing?.qmDbFirstClientMs || 0);
      setSyncStatus(`${roomNo}호 QM 점검 시작${dbMs ? ` · DB ${dbMs}ms` : ''}`);
      void loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 시작 후 화면갱신 실패:', error));
    } catch (error) {
      if (state.qmChecklist.activeInspection === previewActive) state.qmChecklist.activeInspection = null;
      const modalOpen = Boolean($('modalRoot') && !$('modalRoot').classList.contains('hidden'));
      if (modalOpen) closeModal();
      showToast(error?.message || '점검 시작 오류');
    } finally {
      if (button && button.isConnected) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        button.textContent = originalText || '점검 시작';
      }
    }
  }
'''
    text = replace_once(text, old_start, new_start, 'replace normal QM start')

    # 2) Prewarm the existing Realtime/Supabase auth while the QM list is visible.
    old_hydrate = r'''    if (novaRealtimeIsEnabled_() && ['ROOMMAID', 'QM'].includes(mobileRole)) {
      // ROOMMAID/QM은 Sheet 첫 화면 이후 DB의 본인 배정목록을 바로 보정한다.
      void novaRealtimeHydrateCurrentView_();
    } else if (novaRealtimeIsEnabled_() && mobileRole === 'HOUSEMAN') {'''
    new_hydrate = r'''    if (novaRealtimeIsEnabled_() && ['ROOMMAID', 'QM'].includes(mobileRole)) {
      // ROOMMAID/QM은 Sheet 첫 화면 이후 DB의 본인 배정목록을 바로 보정한다.
      void novaRealtimeHydrateCurrentView_();
      // QM_END_TO_END_ACCEL_V1 · 점검버튼을 누르기 전에 DB-first 인증을 준비해 첫 왕복을 줄입니다.
      if (mobileRole === 'QM' && novaRealtime_.qmDraftDbFirstEnabled === true) {
        void novaQmDraftAuthBundle_().catch(error => console.warn('[NOVA QM] 인증 사전준비 지연:', error?.message || error));
      }
    } else if (novaRealtimeIsEnabled_() && mobileRole === 'HOUSEMAN') {'''
    text = replace_once(text, old_hydrate, new_hydrate, 'QM auth prewarm')

    # 3) Wire the already-deployed Supabase QM photo Edge Function into the real Client IIFE.
    photo_anchor = "  async function uploadQmInspectionPhoto_(input) { // (카메라 사진 압축·Drive 등록)\n"
    photo_helpers = r'''  // QM_END_TO_END_ACCEL_V1 · QM 하자사진 Supabase Storage 직접경로
  const NOVA_QM_PHOTO_EDGE_SLUG_ = 'nova-qm-photo-v1';

  function novaQmPhotoDirectEnabled_(active) {
    return Boolean(active?.dbFirst && active?.draft?.draftId
      && novaRealtimeIsEnabled_() && novaRealtime_.qmDraftDbFirstEnabled === true
      && window.supabase?.createClient);
  }

  function novaQmBase64Blob_(base64, mimeType) {
    const binary = atob(String(base64 || ''));
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return new Blob([bytes], { type: mimeType || 'image/jpeg' });
  }

  async function novaQmPhotoEdgeCall_(payload, retryAuth = true) {
    let auth = await novaQmDraftAuthBundle_();
    const send = async currentAuth => {
      const endpoint = `${String(currentAuth.supabaseUrl || '').replace(/\/+$/, '')}/functions/v1/${NOVA_QM_PHOTO_EDGE_SLUG_}`;
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${String(currentAuth.token || '')}`,
          'apikey': String(currentAuth.publishableKey || '')
        },
        body: JSON.stringify(payload || {})
      });
      const data = await response.json().catch(() => ({}));
      return { response, data };
    };
    let result = await send(auth);
    if (result.response.status === 401 && retryAuth) {
      novaRealtime_.qmDraftAuthBundle = null;
      await novaRealtimeSleep_(120);
      auth = await novaQmDraftAuthBundle_();
      result = await send(auth);
    }
    if (!result.response.ok || !result.data?.ok) {
      const error = new Error(result.data?.message || `QM 사진 Storage 오류 (${result.response.status})`);
      error.status = Number(result.response.status || 0);
      error.data = result.data || null;
      throw error;
    }
    return Object.assign({ __auth: auth }, result.data);
  }

  async function novaQmUploadPhotoDbFirst_(active, targetType, targetCode, image) {
    const clientPhotoId = window.crypto?.randomUUID
      ? `qm:${window.crypto.randomUUID()}`
      : `qm:${Date.now()}:${Math.random().toString(36).slice(2)}`;
    let prepared = null;
    try {
      prepared = await novaQmPhotoEdgeCall_({
        action: 'prepare',
        draftId: active.draft.draftId,
        targetType,
        targetCode,
        clientPhotoId,
        fileName: image.fileName,
        mimeType: 'image/jpeg',
        sizeBytes: Math.ceil(String(image.base64 || '').length * 0.75)
      });
      if (!prepared.ready) {
        const auth = prepared.__auth || await novaQmDraftAuthBundle_();
        const storage = window.supabase.createClient(auth.supabaseUrl, auth.publishableKey, {
          auth: { persistSession: false, autoRefreshToken: false }
        });
        const blob = novaQmBase64Blob_(image.base64, 'image/jpeg');
        const { error } = await storage.storage.from(prepared.bucket).uploadToSignedUrl(
          String(prepared.path || ''), String(prepared.token || ''), blob,
          { contentType: 'image/jpeg', upsert: false }
        );
        if (error) throw new Error(error.message || 'QM 사진 Storage 업로드에 실패했습니다.');
      }
      const finalized = await novaQmPhotoEdgeCall_({
        action: 'finalize',
        photoId: String(prepared.photoId || '')
      });
      const serverDraft = finalized.draft || {};
      active.draft = Object.assign({}, active.draft, serverDraft, {
        rowNumber: Number(active.draft?.rowNumber || 0),
        checklistRevision: String(active.draft?.checklistRevision || active.checklist?.revision || ''),
        dbVersion: Number(serverDraft.dbVersion || active.draft?.dbVersion || 0)
      });
      novaQmScheduleLegacyDraftMirror_(active.draft);
      return finalized;
    } catch (error) {
      // prepare 이후 실패한 PENDING 행은 best-effort 정리하고 검증된 Drive fallback으로 내려갑니다.
      if (prepared?.photoId && !prepared?.ready) {
        try { await novaQmPhotoEdgeCall_({ action: 'delete', photoId: String(prepared.photoId) }, false); }
        catch (cleanupError) { console.warn('[NOVA QM] 실패 사진 PENDING 정리 지연:', cleanupError?.message || cleanupError); }
      }
      throw error;
    }
  }

'''
    text = replace_once(text, photo_anchor, photo_helpers + photo_anchor, 'insert direct QM photo helpers')

    old_upload = r'''  async function uploadQmInspectionPhoto_(input) { // (카메라 사진 압축·Drive 등록)
    const file = input.files?.[0];
    if (!file) return;
    const card = input.closest('[data-qm-check-code], [data-qm-defect-id]');
    const targetType = card.hasAttribute('data-qm-check-code') ? 'ITEM' : 'DEFECT';
    const targetCode = card.dataset.qmCheckCode || card.dataset.qmDefectId;
    input.disabled = true;
    try {
      await saveQmInspectionDraftNow_(false);
      const image = await compressQmPhotoFile_(file);
      const active = state.qmChecklist.activeInspection;
      const result = await callServer('uploadQmInspectionPhoto', state.token, {
        draftId: active.draft.draftId, targetType, targetCode,
        fileName: image.fileName, mimeType: image.mimeType, base64: image.base64
      });
      if (!result?.ok) throw new Error(result?.message || '사진을 등록하지 못했습니다.');
      active.draft = result.draft || active.draft;
      showToast('하자 사진을 등록했습니다.');
      openQmInspectionModal_();
    } catch (error) { showToast(error?.message || '사진 등록 오류'); input.disabled = false; input.value = ''; }
  }
'''
    new_upload = r'''  async function uploadQmInspectionPhoto_(input) { // (QM_END_TO_END_ACCEL_V1 · DB-first Storage + Drive 안전 fallback)
    const file = input.files?.[0];
    if (!file) return;
    const card = input.closest('[data-qm-check-code], [data-qm-defect-id]');
    if (!card) return;
    const targetType = card.hasAttribute('data-qm-check-code') ? 'ITEM' : 'DEFECT';
    const targetCode = card.dataset.qmCheckCode || card.dataset.qmDefectId;
    input.disabled = true;
    try {
      const active = state.qmChecklist.activeInspection;
      if (!active) throw new Error('진행 중인 점검이 없습니다.');

      // 현재 체크내용 DB 저장과 사진 압축은 서로 독립이므로 병렬 처리합니다.
      const [saveResult, image] = await Promise.all([
        saveQmInspectionDraftNow_(false),
        compressQmPhotoFile_(file)
      ]);

      if (novaQmPhotoDirectEnabled_(active) && saveResult?.ok) {
        try {
          await novaQmUploadPhotoDbFirst_(active, targetType, targetCode, image);
          showToast('하자 사진을 빠르게 등록했습니다.');
          openQmInspectionModal_();
          return;
        } catch (directError) {
          console.warn('[NOVA QM] 하자사진 직접 Storage 실패 · Drive 안전경로 사용:', directError?.message || directError);
          // Drive fallback은 동일 draftId의 Sheet 이력이 준비된 뒤에만 실행합니다.
          await novaQmEnsureDbFirstMirror_(active);
        }
      }

      await ensureQmInspectionDraftReady_(active);
      const result = await callServer('uploadQmInspectionPhoto', state.token, {
        draftId: active.draft.draftId, targetType, targetCode,
        fileName: image.fileName, mimeType: image.mimeType, base64: image.base64
      });
      if (!result?.ok) throw new Error(result?.message || '사진을 등록하지 못했습니다.');
      active.draft = result.draft || active.draft;
      showToast('하자 사진을 등록했습니다.');
      openQmInspectionModal_();
    } catch (error) {
      showToast(error?.message || '사진 등록 오류');
      input.disabled = false;
      input.value = '';
    }
  }
'''
    text = replace_once(text, old_upload, new_upload, 'replace QM photo upload')

    old_delete = r'''  async function deleteQmInspectionPhoto_(button) { // (등록사진 삭제)
    const active = state.qmChecklist.activeInspection;
    if (!active?.draft?.draftId) return;
    button.disabled = true;
    try {
      const result = await callServer('deleteQmInspectionPhoto', state.token, {
        draftId: active.draft.draftId, targetType: button.dataset.targetType,
        targetCode: button.dataset.targetCode, fileId: button.dataset.qmPhotoDelete
      });
      if (!result?.ok) throw new Error(result?.message || '사진을 삭제하지 못했습니다.');
      active.draft = result.draft || active.draft;
      openQmInspectionModal_();
    } catch (error) { showToast(error?.message || '사진 삭제 오류'); button.disabled = false; }
  }
'''
    new_delete = r'''  async function deleteQmInspectionPhoto_(button) { // (QM_END_TO_END_ACCEL_V1 · Storage/Drive 사진 삭제 호환)
    const active = state.qmChecklist.activeInspection;
    if (!active?.draft?.draftId) return;
    const fileId = String(button.dataset.qmPhotoDelete || '').trim();
    button.disabled = true;
    try {
      if (fileId.startsWith('sbqm:') && novaRealtimeIsEnabled_()) {
        const result = await novaQmPhotoEdgeCall_({ action: 'delete', photoId: fileId });
        const serverDraft = result.draft || {};
        active.draft = Object.assign({}, active.draft, serverDraft, {
          rowNumber: Number(active.draft?.rowNumber || 0),
          checklistRevision: String(active.draft?.checklistRevision || active.checklist?.revision || ''),
          dbVersion: Number(serverDraft.dbVersion || active.draft?.dbVersion || 0)
        });
        novaQmScheduleLegacyDraftMirror_(active.draft);
        openQmInspectionModal_();
        return;
      }
      const result = await callServer('deleteQmInspectionPhoto', state.token, {
        draftId: active.draft.draftId, targetType: button.dataset.targetType,
        targetCode: button.dataset.targetCode, fileId
      });
      if (!result?.ok) throw new Error(result?.message || '사진을 삭제하지 못했습니다.');
      active.draft = result.draft || active.draft;
      openQmInspectionModal_();
    } catch (error) { showToast(error?.message || '사진 삭제 오류'); button.disabled = false; }
  }
'''
    text = replace_once(text, old_delete, new_delete, 'replace QM photo delete')

    old_view = r'''  async function openQmPhotoViewer_(fileId) { // (권한검증 사진 새창 보기)
    const win = window.open('', '_blank');
    if (!win) return showToast('브라우저에서 팝업을 허용해 주세요.');
    win.document.write('<title>QM 사진 불러오는 중</title><style>body{font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0}</style><p>사진을 불러오는 중입니다.</p>');
    win.document.close();
    try {
      const result = await callServer('getQmInspectionPhoto', state.token, { fileId });
      if (!result?.ok) throw new Error(result?.message || '사진을 불러오지 못했습니다.');
      win.document.open();
      win.document.write(`<title>${escapeHtml(result.name || 'QM 사진')}</title><style>body{margin:0;background:#111;display:grid;place-items:center;min-height:100vh}img{max-width:100%;max-height:100vh;object-fit:contain}</style><img src="${result.dataUrl}">`);
      win.document.close();
    } catch (error) {
      try { win.close(); } catch (_) {}
      showToast(error?.message || '사진 조회 오류');
    }
  }
'''
    new_view = r'''  async function openQmPhotoViewer_(fileId) { // (QM_END_TO_END_ACCEL_V1 · Storage/Drive 사진 조회 호환)
    const safeFileId = String(fileId || '').trim();
    const win = window.open('', '_blank');
    if (!win) return showToast('브라우저에서 팝업을 허용해 주세요.');
    win.document.write('<title>QM 사진 불러오는 중</title><style>body{font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0}</style><p>사진을 불러오는 중입니다.</p>');
    win.document.close();
    try {
      let name = 'QM 사진';
      let src = '';
      if (safeFileId.startsWith('sbqm:') && novaRealtimeIsEnabled_()) {
        const result = await novaQmPhotoEdgeCall_({ action: 'view', photoId: safeFileId });
        name = result.photo?.name || name;
        src = String(result.signedUrl || '');
      } else {
        const result = await callServer('getQmInspectionPhoto', state.token, { fileId: safeFileId });
        if (!result?.ok) throw new Error(result?.message || '사진을 불러오지 못했습니다.');
        name = result.name || name;
        src = String(result.dataUrl || '');
      }
      if (!src) throw new Error('사진 조회 주소를 확인하지 못했습니다.');
      win.document.open();
      win.document.write(`<title>${escapeHtml(name)}</title><style>body{margin:0;background:#111;display:grid;place-items:center;min-height:100vh}img{max-width:100%;max-height:100vh;object-fit:contain}</style><img src="${src}">`);
      win.document.close();
    } catch (error) {
      try { win.close(); } catch (_) {}
      showToast(error?.message || '사진 조회 오류');
    }
  }
'''
    text = replace_once(text, old_view, new_view, 'replace QM photo viewer')

    # 4) Make the already-existing QM_REWORK safe branch reachable and avoid a full snapshot after success.
    text = replace_once(
        text,
        "    const mappedAction = roommaidMobileOperation && rawAction === 'START' ? 'CLEANING_START'\n      : roommaidMobileOperation && rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'\n      : rawAction;",
        "    let mappedAction = roommaidMobileOperation && rawAction === 'START' ? 'CLEANING_START'\n      : roommaidMobileOperation && rawAction === 'COMPLETE' ? 'CLEANING_COMPLETE'\n      : rawAction;",
        'make mappedAction mutable'
    )
    text = replace_once(
        text,
        "    const currentRole = String(state.bootstrap?.user?.role || '').trim().toUpperCase();\n    const housemanWorkerAction = legacyMethod === 'updateHousemanOrder'",
        "    const currentRole = String(state.bootstrap?.user?.role || '').trim().toUpperCase();\n    if (roommaidMobileOperation && currentRole === 'QM' && rawAction === 'REWORK') mappedAction = 'QM_REWORK'; // QM_END_TO_END_ACCEL_V1\n    const housemanWorkerAction = legacyMethod === 'updateHousemanOrder'",
        'activate QM_REWORK safe branch'
    )

    text = replace_once(
        text,
        "    const roommaidFastPath = method === 'updateMobileRoomOperation' && role === 'ROOMMAID'\n      && ['START', 'COMPLETE'].includes(action);\n    const housemanRollback = housemanFastPath ? applyOptimisticHousemanOrder_(safePayload) : null;",
        "    const roommaidFastPath = method === 'updateMobileRoomOperation' && role === 'ROOMMAID'\n      && ['START', 'COMPLETE'].includes(action);\n    const qmReworkFastPath = method === 'updateMobileRoomOperation' && role === 'QM' && action === 'REWORK'; // QM_END_TO_END_ACCEL_V1\n    const housemanRollback = housemanFastPath ? applyOptimisticHousemanOrder_(safePayload) : null;",
        'define QM rework fast post-success path'
    )
    text = replace_once(
        text,
        "      } else if (roommaidFastPath && result.room) {\n        upsertMobileRoommaidRoomLocal_(result.room);\n        refreshRoommaidMobileSummaryLocal_();\n        renderMobileSummary();\n        renderMobileList();\n        setSyncStatus(`룸메이드 즉시 저장 · ${result.room.updatedAt || ''}`);\n      } else {\n        await loadMobileSnapshot({ silent: true, force: true });\n      }",
        "      } else if (roommaidFastPath && result.room) {\n        upsertMobileRoommaidRoomLocal_(result.room);\n        refreshRoommaidMobileSummaryLocal_();\n        renderMobileSummary();\n        renderMobileList();\n        setSyncStatus(`룸메이드 즉시 저장 · ${result.room.updatedAt || ''}`);\n      } else if (qmReworkFastPath && result.room) {\n        applyQmRealtimeRoomLocal_(safePayload.roomNo, result.room);\n        setSyncStatus(`${safePayload.roomNo}호 재정비 요청 저장`);\n      } else {\n        await loadMobileSnapshot({ silent: true, force: true });\n      }",
        'avoid full snapshot after QM rework'
    )

    CLIENT.write_text(text, encoding='utf-8')
    print('Applied QM_END_TO_END_ACCEL_V1 to Client.html.')


if __name__ == '__main__':
    main()
