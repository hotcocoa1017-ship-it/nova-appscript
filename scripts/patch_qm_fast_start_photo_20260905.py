#!/usr/bin/env python3
from pathlib import Path
import re

MARKER = 'QM_FAST_START_PHOTO_V1'
ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding='utf-8')


def write(name, text):
    (ROOT / name).write_text(text, encoding='utf-8')


def function_segment(text, start_marker, next_marker):
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f'missing marker: {start_marker}')
    end = text.find(next_marker, start + len(start_marker))
    if end < 0:
        raise SystemExit(f'missing next marker: {next_marker}')
    return start, end, text[start:end]


def patch_index():
    text = read('Index.html')
    include = "  <?!= include_('QmFastPathClient'); ?> <!-- QM_FAST_START_PHOTO_V1 -->"
    if include not in text:
        anchor = "  <?!= include_('Client'); ?>"
        if anchor not in text:
            raise SystemExit('Index Client include anchor missing')
        text = text.replace(anchor, anchor + '\n' + include, 1)
        write('Index.html', text)


def patch_browse_start(text):
    start, end, seg = function_segment(
        text,
        '  async function startQmBrowseInspection_(roomNo, button)',
        '\n  async function '
    )
    if 'NOVA_QM_FAST.startBrowse' in seg:
        return text
    pattern = re.compile(
        r"(?P<indent>\s*)const result = await callServer\('startQmMobileBrowseInspection', state\.token, \{(?P<body>.*?)\n(?P=indent)\}\);",
        re.S,
    )
    match = pattern.search(seg)
    if not match:
        raise SystemExit('QM browse start callServer block missing')
    indent = match.group('indent')
    body = match.group('body')
    replacement = (
        f"{indent}// QM_FAST_START_PHOTO_V1 · 추가탭 본인확보는 PostgreSQL 원자처리, Apps Script는 장애 fallback\n"
        f"{indent}const qmBrowsePayload = {{{body}\n{indent}}};\n"
        f"{indent}let result;\n"
        f"{indent}try {{\n"
        f"{indent}  if (!window.NOVA_QM_FAST || !novaRealtimeIsEnabled_()) throw new Error('QM DB 빠른시작을 사용할 수 없습니다.');\n"
        f"{indent}  const auth = await novaQmDraftAuthBundle_();\n"
        f"{indent}  result = await window.NOVA_QM_FAST.startBrowse(auth, Object.assign({{}}, qmBrowsePayload, {{\n"
        f"{indent}    requestId: novaRealtimeRequestId_('QM_BROWSE_START', room.roomNo)\n"
        f"{indent}  }}));\n"
        f"{indent}}} catch (fastError) {{\n"
        f"{indent}  console.warn('[NOVA QM] 추가탭 DB 빠른시작 실패 · 기존 경로 fallback', fastError);\n"
        f"{indent}  result = await callServer('startQmMobileBrowseInspection', state.token, qmBrowsePayload);\n"
        f"{indent}}}"
    )
    seg = seg[:match.start()] + replacement + seg[match.end():]
    return text[:start] + seg + text[end:]


def patch_upload(text):
    start, end, seg = function_segment(
        text,
        '  async function uploadQmInspectionPhoto_(input)',
        '\n  async function compressQmPhotoFile_'
    )
    if 'NOVA_QM_FAST.uploadPhoto' in seg:
        return text
    new_seg = r'''  async function uploadQmInspectionPhoto_(input) { // QM_FAST_START_PHOTO_V1 · Private Storage 직접등록 + Drive fallback
    const file = input.files?.[0];
    if (!file) return;
    const card = input.closest('[data-qm-check-code], [data-qm-defect-id]');
    if (!card) return showToast('사진을 연결할 점검 항목을 찾지 못했습니다.');
    const targetType = card.hasAttribute('data-qm-check-code') ? 'ITEM' : 'DEFECT';
    const targetCode = card.dataset.qmCheckCode || card.dataset.qmDefectId;
    input.disabled = true;
    try {
      await ensureQmInspectionDraftReady_(state.qmChecklist.activeInspection);
      await saveQmInspectionDraftNow_(false);
      const image = await compressQmPhotoFile_(file);
      const active = state.qmChecklist.activeInspection;
      if (!active?.draft?.draftId) throw new Error('체크리스트 저장준비가 완료되지 않았습니다. 다시 시도하세요.');

      if (window.NOVA_QM_FAST && novaRealtimeIsEnabled_()) {
        try {
          const auth = await novaQmDraftAuthBundle_();
          const direct = await window.NOVA_QM_FAST.uploadPhoto(auth, {
            draftId: active.draft.draftId,
            targetType,
            targetCode,
            fileName: image.fileName,
            mimeType: image.mimeType,
            base64: image.base64,
            clientPhotoId: novaRealtimeRequestId_('QM_PHOTO', active.roomNo)
          });
          if (!direct?.ok || !direct?.draft) throw new Error(direct?.message || 'QM 사진 저장 완료값을 확인하지 못했습니다.');
          active.draft = Object.assign({}, active.draft, direct.draft, {
            answers: direct.draft.answers || active.draft.answers || [],
            defects: direct.draft.defects || active.draft.defects || [],
            dbVersion: Number(direct.draft.dbVersion || active.draft.dbVersion || 0),
            dbSavedAt: String(direct.draft.savedAt || active.draft.dbSavedAt || '')
          });
          novaQmScheduleLegacyDraftMirror_(active.draft);
          showToast('하자 사진을 등록했습니다.');
          openQmInspectionModal_();
          return;
        } catch (directError) {
          console.warn('[NOVA QM] Private Storage 사진등록 실패 · 기존 Drive 경로 fallback', directError);
        }
      }

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
    return text[:start] + new_seg + text[end:]


def patch_delete(text):
    start, end, seg = function_segment(
        text,
        '  async function deleteQmInspectionPhoto_(button)',
        '\n  async function openQmPhotoViewer_'
    )
    if 'NOVA_QM_FAST.deletePhoto' in seg:
        return text
    new_seg = r'''  async function deleteQmInspectionPhoto_(button) { // QM_FAST_START_PHOTO_V1 · Storage/Drive 이중호환 삭제
    const active = state.qmChecklist.activeInspection;
    if (!active?.draft?.draftId) return;
    const fileId = String(button.dataset.qmPhotoDelete || '');
    button.disabled = true;
    try {
      if (/^sbqm:/i.test(fileId)) {
        if (!window.NOVA_QM_FAST || !novaRealtimeIsEnabled_()) throw new Error('QM Storage 사진 삭제 모듈을 사용할 수 없습니다.');
        const auth = await novaQmDraftAuthBundle_();
        const direct = await window.NOVA_QM_FAST.deletePhoto(auth, fileId);
        if (!direct?.ok || !direct?.draft) throw new Error(direct?.message || '사진을 삭제하지 못했습니다.');
        active.draft = Object.assign({}, active.draft, direct.draft, {
          answers: direct.draft.answers || [],
          defects: direct.draft.defects || [],
          dbVersion: Number(direct.draft.dbVersion || active.draft.dbVersion || 0),
          dbSavedAt: String(direct.draft.savedAt || active.draft.dbSavedAt || '')
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
    return text[:start] + new_seg + text[end:]


def patch_viewer(text):
    start, end, seg = function_segment(
        text,
        '  async function openQmPhotoViewer_(fileId)',
        '\n  function '
    )
    if 'NOVA_QM_FAST.viewPhoto' in seg:
        return text
    old = "      const result = await callServer('getQmInspectionPhoto', state.token, { fileId });"
    if old not in seg:
        raise SystemExit('QM photo viewer server call missing')
    new = """      let result;
      if (/^sbqm:/i.test(String(fileId || ''))) {
        if (!window.NOVA_QM_FAST || !novaRealtimeIsEnabled_()) throw new Error('QM Storage 사진 조회 모듈을 사용할 수 없습니다.');
        const auth = await novaQmDraftAuthBundle_();
        const direct = await window.NOVA_QM_FAST.viewPhoto(auth, fileId);
        result = { ok: Boolean(direct?.ok && direct?.signedUrl), name: direct?.photo?.name || 'QM 사진', dataUrl: direct?.signedUrl || '' };
      } else {
        result = await callServer('getQmInspectionPhoto', state.token, { fileId });
      }"""
    seg = seg.replace(old, new, 1)
    return text[:start] + seg + text[end:]


def patch_client():
    text = read('Client.html')
    text = patch_browse_start(text)
    text = patch_upload(text)
    text = patch_delete(text)
    text = patch_viewer(text)
    write('Client.html', text)


def patch_qm_server():
    text = read('16_QmChecklist.js')
    if 'QM_REALTIME_STALE_SHEET_VERIFY_V1' in text:
        return
    old = """      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      if (String(rowInfo.data['QM사번'] || '').trim() !== user.employeeNo) throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');
      const currentStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
      if (!['QM_WAITING', 'COMPLETED', 'QM_CHECKING'].includes(currentStatus)) throw new Error('QM 점검대기 또는 점검중 객실만 시작할 수 있습니다.');"""
    new = """      if (!rowInfo) throw new Error('현재객실현황에서 해당 객실을 찾을 수 없습니다.');
      const sheetQmEmployeeNo = String(rowInfo.data['QM사번'] || '').trim();
      let currentStatus = String(rowInfo.data['청소상태'] || '').trim().toUpperCase();
      if (sheetQmEmployeeNo !== user.employeeNo) { // QM_REALTIME_STALE_SHEET_VERIFY_V1
        if (!realtimeStarted || typeof novaRealtimeFetchCurrentRoomForQmMirror_ !== 'function') {
          throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');
        }
        let dbRoom = null;
        try { dbRoom = novaRealtimeFetchCurrentRoomForQmMirror_(token, businessDate, site, roomNo); }
        catch (dbError) { throw new Error('QM 실시간 배정확인을 완료하지 못했습니다. 잠시 후 다시 시도하세요.'); }
        const dbQmEmployeeNo = String(dbRoom && dbRoom.qmEmployeeNo || '').trim();
        const dbCleaningStatus = String(dbRoom && dbRoom.cleaningStatus || '').trim().toUpperCase();
        if (dbQmEmployeeNo !== user.employeeNo || dbCleaningStatus !== 'QM_CHECKING') {
          throw new Error('본인에게 배정된 객실만 점검할 수 있습니다.');
        }
        currentStatus = dbCleaningStatus;
      }
      if (!['QM_WAITING', 'COMPLETED', 'QM_CHECKING'].includes(currentStatus)) throw new Error('QM 점검대기 또는 점검중 객실만 시작할 수 있습니다.');"""
    if old not in text:
        raise SystemExit('startQmInspection assignment validation anchor missing')
    text = text.replace(old, new, 1)
    write('16_QmChecklist.js', text)


def patch_realtime_mirror():
    text = read('RealtimeDailySync.js')
    if 'QM_START_MIRROR_ASSIGNMENT_V1' in text:
        return
    old = """        roomUpdates.push({
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: afterStatus,
          version,
          updatedAt: nowText_()
        });
        rowInfo.data['청소상태'] = afterStatus;
        rowInfo.data['마지막변경버전'] = version;
        if (action === 'QM_START') {"""
    new = """        const qmRoomUpdate = { // QM_START_MIRROR_ASSIGNMENT_V1
          rowNumber: rowInfo.rowNumber,
          cleaningStatus: afterStatus,
          version,
          updatedAt: nowText_()
        };
        if (action === 'QM_START') qmRoomUpdate.qmEmployeeNo = employeeNo;
        roomUpdates.push(qmRoomUpdate);
        rowInfo.data['청소상태'] = afterStatus;
        rowInfo.data['마지막변경버전'] = version;
        if (action === 'QM_START') rowInfo.data['QM사번'] = employeeNo;
        if (action === 'QM_START') {"""
    if old not in text:
        raise SystemExit('Realtime QM event mirror anchor missing')
    text = text.replace(old, new, 1)
    write('RealtimeDailySync.js', text)


def patch_deploy_workflow():
    name = '.github/workflows/deploy-apps-script.yml'
    text = read(name)
    apply_step = """      - name: Apply QM fast start and private photo V1
        run: python3 scripts/patch_qm_fast_start_photo_20260905.py

"""
    if 'Apply QM fast start and private photo V1' not in text:
        anchor = """      - name: Apply mobile full view state persistence V2
        run: python3 scripts/patch_mobile_view_state_persistence_20260904.py

"""
        if anchor not in text: raise SystemExit('deploy apply-step anchor missing')
        text = text.replace(anchor, anchor + apply_step, 1)

    validate_step = """      - name: Validate QM fast start and private photo V1
        run: python3 scripts/validate_qm_fast_start_photo_20260905.py

"""
    if 'Validate QM fast start and private photo V1' not in text:
        anchor = """      - name: Validate ORDER shared site simulations
        run: python3 scripts/validate_order_site_context_v1.py

"""
        if anchor not in text: raise SystemExit('deploy validation-step anchor missing')
        text = text.replace(anchor, anchor + validate_step, 1)

    if "('QmFastPathClient.html', '/tmp/NovaQmFast.js')" not in text:
        anchor = """              ('Client.html', '/tmp/NovaClient.js'),
              ('HousemanUiPerformancePatch.html', '/tmp/NovaNotification.js'),"""
        replacement = """              ('Client.html', '/tmp/NovaClient.js'),
              ('HousemanUiPerformancePatch.html', '/tmp/NovaNotification.js'),
              ('QmFastPathClient.html', '/tmp/NovaQmFast.js'),"""
        if anchor not in text: raise SystemExit('deploy JS tuple anchor missing')
        text = text.replace(anchor, replacement, 1)
    if 'node --check /tmp/NovaQmFast.js' not in text:
        anchor = '          node --check /tmp/NovaNotification.js\n'
        if anchor not in text: raise SystemExit('deploy node-check anchor missing')
        text = text.replace(anchor, anchor + '          node --check /tmp/NovaQmFast.js\n', 1)

    tracked_old = "tracked=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)"
    tracked_new = "tracked=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html QmFastPathClient.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)"
    if tracked_old in text:
        text = text.replace(tracked_old, tracked_new, 1)

    idemp_anchor = '          python3 scripts/patch_mobile_view_state_persistence_20260904.py\n'
    idemp_line = '          python3 scripts/patch_qm_fast_start_photo_20260905.py\n'
    # The first occurrence is the normal apply step (different indentation context); insert only in the idempotence command list.
    if text.count(idemp_line) < 1:
        raise SystemExit('deploy normal QM patch step was not inserted')
    if text.count(idemp_line) < 2:
        pos = text.rfind(idemp_anchor)
        if pos < 0: raise SystemExit('deploy idempotence anchor missing')
        pos += len(idemp_anchor)
        text = text[:pos] + idemp_line + text[pos:]

    generated_old = 'generated=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)'
    generated_new = 'generated=(Index.html 02_Repository.js 03_Auth.js 05_Performance.js 10_Mobile.js 16_QmChecklist.js QmMobileBrowse.js Client.html QmFastPathClient.html HousemanUiPerformancePatch.html RealtimeDailySync.js 17_RoommaidPerformance.js 19_RoommaidCloseJournal.js)'
    if generated_old in text:
        text = text.replace(generated_old, generated_new, 1)
    write(name, text)


def main():
    patch_index()
    patch_client()
    patch_qm_server()
    patch_realtime_mirror()
    patch_deploy_workflow()
    print('QM_FAST_START_PHOTO_PATCH=PASS')


if __name__ == '__main__':
    main()
