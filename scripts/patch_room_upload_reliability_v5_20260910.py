from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
room_path = ROOT / '09_RoomStatusUpload.js'
client_path = ROOT / 'Client.html'
rt_path = ROOT / 'RealtimeDailySync.js'

room = room_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')
rt = rt_path.read_text(encoding='utf-8')

# 1) Keep recovery plans long enough for crash/reload recovery.
old_ttl = "PREVIEW_STORE_TTL_MS: 60 * 60 * 1000,"
new_ttl = "PREVIEW_STORE_TTL_MS: 24 * 60 * 60 * 1000, // ROOM_UPLOAD_RECOVERY_TTL_V1"
if old_ttl in room:
    room = room.replace(old_ttl, new_ttl, 1)
elif new_ttl not in room:
    raise SystemExit('preview TTL marker not found')

# 2) Add a short pre-commit hold and a durable post-commit hold so stale Sheet->DB sync cannot overtake a DB-first upload.
hold_helpers = r'''
// ROOM_UPLOAD_FORWARD_SYNC_HOLD_V1
const NOVA_ROOM_UPLOAD_FORWARD_HOLD_PREFIX_ = 'NOVA_ROOM_UPLOAD_FORWARD_HOLD_UNTIL_';
function roomUploadForwardHoldKey_(businessDate, site) {
  return `${NOVA_ROOM_UPLOAD_FORWARD_HOLD_PREFIX_}${String(businessDate || '').trim()}|${String(site || '').trim()}`;
}
function setRoomUploadRealtimeForwardHold_(businessDate, site, ttlMs) {
  const dateText = String(businessDate || '').trim();
  const siteText = String(site || '').trim();
  if (!dateText || !siteText) return 0;
  const until = Date.now() + Math.max(60 * 1000, Number(ttlMs || 0));
  PropertiesService.getScriptProperties().setProperty(roomUploadForwardHoldKey_(dateText, siteText), String(until));
  return until;
}
function clearRoomUploadRealtimeForwardHold_(businessDate, site) {
  const dateText = String(businessDate || '').trim();
  const siteText = String(site || '').trim();
  if (!dateText || !siteText) return;
  PropertiesService.getScriptProperties().deleteProperty(roomUploadForwardHoldKey_(dateText, siteText));
}
function isRoomUploadRealtimeForwardHeld_(businessDate, site) {
  const key = roomUploadForwardHoldKey_(businessDate, site);
  const props = PropertiesService.getScriptProperties();
  const until = Number(props.getProperty(key) || 0);
  if (!until) return false;
  if (until <= Date.now()) {
    props.deleteProperty(key);
    return false;
  }
  return true;
}
function markRoomUploadDbCommittedHold(token, payload) {
  const user = requireRole_(token, ['ADMIN', 'ORDER']);
  const safe = payload || {};
  const businessDate = normalizeBusinessDate_(safe.businessDate);
  const site = String(safe.site || '').trim();
  if (!site) throw new Error('객실업로드 DB 확정 보호에 사업장이 필요합니다.');
  const until = setRoomUploadRealtimeForwardHold_(businessDate, site, 24 * 60 * 60 * 1000);
  return { ok: true, businessDate, site, until, requestedBy: user.employeeNo };
}
'''
if 'ROOM_UPLOAD_FORWARD_SYNC_HOLD_V1' not in room:
    anchor = "// ROOM_UPLOAD_DB_FIRST_APP_V4\n"
    if anchor not in room:
        raise SystemExit('DB-first anchor not found')
    room = room.replace(anchor, hold_helpers + '\n' + anchor, 1)

# Set short protection before handing the plan to the client. If the user cancels, it self-expires.
plan_save = "    saveRoomUploadPreview_(planId, plan);\n\n    return {"
plan_save_new = "    saveRoomUploadPreview_(planId, plan);\n    setRoomUploadRealtimeForwardHold_(plan.businessDate, plan.site, 15 * 60 * 1000); // ROOM_UPLOAD_FORWARD_SYNC_HOLD_V1\n\n    return {"
if plan_save in room:
    room = room.replace(plan_save, plan_save_new, 1)
elif 'setRoomUploadRealtimeForwardHold_(plan.businessDate, plan.site, 15 * 60 * 1000)' not in room:
    raise SystemExit('plan save anchor not found')

# 3) Canonical DB-first Sheet mirror: append a new date/site block; never rewrite the accumulated history sheet.
old_db_write = """      const targetRowsContiguous = targetRowNumbers.length === newRows.length
        && targetRowNumbers.length > 0
        && targetRowNumbers.every((rowNumber, index) => rowNumber === targetRowNumbers[0] + index);
      let roomWriteMode = 'FULL_REWRITE';
      let firstWrittenRow = keptRows.length + 2;
      if (targetRowsContiguous) {
        firstWrittenRow = targetRowNumbers[0];
        ensureSheetRowCapacity_(sheet, firstWrittenRow + newRows.length - 1);
        sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows);
        roomWriteMode = 'IN_PLACE_BLOCK';
      } else {
        const allRows = keptRows.concat(newRows);
        if (sheet.getLastRow() > 1) {
          sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).clearContent();
        }
        if (allRows.length) {
          ensureSheetRowCapacity_(sheet, allRows.length + 1);
          sheet.getRange(2, 1, allRows.length, lastColumn).setValues(allRows);
        }
      }

      const updatedAt = nowText_();
      const maintenanceReset = plan.resetExisting
        ? resetRoomMaintenanceHistoryForUpload_(plan.businessDate, plan.site, updatedAt)
        : createRoomMaintenanceResetSummary_();
      SpreadsheetApp.flush();
"""
new_db_write = """      const targetRowsContiguous = targetRowNumbers.length === newRows.length
        && targetRowNumbers.length > 0
        && targetRowNumbers.every((rowNumber, index) => rowNumber === targetRowNumbers[0] + index);
      let roomWriteMode = '';
      let firstWrittenRow = 0;
      if (targetRowNumbers.length === 0) {
        firstWrittenRow = Math.max(2, sheet.getLastRow() + 1);
        ensureSheetRowCapacity_(sheet, firstWrittenRow + newRows.length - 1);
        sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows);
        roomWriteMode = 'APPEND_NEW_BLOCK'; // ROOM_UPLOAD_APPEND_NEW_BLOCK_V1
      } else if (targetRowsContiguous) {
        firstWrittenRow = targetRowNumbers[0];
        ensureSheetRowCapacity_(sheet, firstWrittenRow + newRows.length - 1);
        sheet.getRange(firstWrittenRow, 1, newRows.length, lastColumn).setValues(newRows);
        roomWriteMode = 'IN_PLACE_BLOCK';
      } else {
        throw new Error(`현재객실현황 ${plan.businessDate} · ${plan.site} 블록 구조가 비정상입니다. 누적 시트 전체 재작성은 안전상 중단했습니다. (기존 ${targetRowNumbers.length}행 / 예정 ${newRows.length}행)`); // ROOM_UPLOAD_MIRROR_FAIL_CLOSED_V1
      }

      SpreadsheetApp.flush();
      verifyRoomStatusUploadMirrorBlock_(sheet, firstWrittenRow, newRows, headerMap, lastColumn, plan.businessDate, plan.site); // ROOM_UPLOAD_MIRROR_READBACK_V1

      const updatedAt = nowText_();
      const maintenanceReset = plan.resetExisting
        ? resetRoomMaintenanceHistoryForUpload_(plan.businessDate, plan.site, updatedAt)
        : createRoomMaintenanceResetSummary_();
      SpreadsheetApp.flush();
"""
if old_db_write in room:
    room = room.replace(old_db_write, new_db_write, 1)
elif 'ROOM_UPLOAD_APPEND_NEW_BLOCK_V1' not in room:
    raise SystemExit('canonical DB-first write block not found')

# Read-back verifier is intentionally before maintenance/history side effects.
verify_helper = r'''
// ROOM_UPLOAD_MIRROR_READBACK_V1
function verifyRoomStatusUploadMirrorBlock_(sheet, firstWrittenRow, expectedRows, headerMap, lastColumn, businessDate, site) {
  const rows = Array.isArray(expectedRows) ? expectedRows : [];
  if (!rows.length || !Number(firstWrittenRow)) throw new Error('객실업로드 Sheet 검증 대상이 없습니다.');
  const actualRows = sheet.getRange(Number(firstWrittenRow), 1, rows.length, Number(lastColumn)).getDisplayValues();
  if (actualRows.length !== rows.length) throw new Error('객실업로드 Sheet 반영 행수 검증에 실패했습니다.');
  const fields = [
    '업무일자','사업장','객실번호','객실상태','마지막객실상태','이전객실상태','이전청소상태',
    '이전룸메이드사번','이전보조룸메이드사번','청소상태','정비유형','배정유형','룸메이드사번',
    '보조룸메이드사번','QM사번','마지막변경버전','동','객실운영상태','선배정여부','VIP여부','중요객실여부'
  ];
  const seen = new Set();
  rows.forEach((expectedRow, index) => {
    const expected = rowObjectFromValues_(expectedRow, headerMap);
    const actual = rowObjectFromValues_(actualRows[index], headerMap);
    const roomNo = normalizeRoomNo_(actual['객실번호']);
    if (!roomNo || seen.has(roomNo)) throw new Error(`객실업로드 Sheet 검증 실패: ${index + 1}번째 행 객실번호가 누락 또는 중복입니다.`);
    seen.add(roomNo);
    fields.forEach(field => {
      const expectedText = String(expected[field] ?? '').trim();
      const actualText = String(actual[field] ?? '').trim();
      if (expectedText !== actualText) {
        throw new Error(`객실업로드 Sheet 검증 실패: ${roomNo}호 ${field} 값이 DB 확정값과 다릅니다.`);
      }
    });
  });
  if (seen.size !== rows.length) throw new Error('객실업로드 Sheet 검증 실패: 객실 수가 일치하지 않습니다.');
  if ([...seen].some(roomNo => !/^\d{4}$/.test(roomNo))) throw new Error('객실업로드 Sheet 검증 실패: 객실번호 형식이 올바르지 않습니다.');
  const first = rowObjectFromValues_(actualRows[0], headerMap);
  if (String(first['업무일자'] || '').trim() !== String(businessDate || '').trim() || String(first['사업장'] || '').trim() !== String(site || '').trim()) {
    throw new Error('객실업로드 Sheet 검증 실패: 업무일자 또는 사업장이 일치하지 않습니다.');
  }
  return { ok: true, rows: seen.size };
}
'''
if 'function verifyRoomStatusUploadMirrorBlock_' not in room:
    anchor = "\nfunction applyRoomStatusUpload(token, previewId, options)"
    if anchor not in room:
        raise SystemExit('legacy function anchor not found')
    room = room.replace(anchor, '\n' + verify_helper + anchor, 1)

# Clear stale-forward protection only after DB-confirmed Sheet mirror + side effects have succeeded.
cleanup_anchor = "      removeRoomUploadPreview_(planId, true);\n      removeRoomUploadPreview_(previewId, true);\n      return result;"
cleanup_new = "      clearRoomUploadRealtimeForwardHold_(plan.businessDate, plan.site); // ROOM_UPLOAD_FORWARD_SYNC_HOLD_V1\n      removeRoomUploadPreview_(planId, true);\n      removeRoomUploadPreview_(previewId, true);\n      return result;"
if cleanup_anchor in room:
    room = room.replace(cleanup_anchor, cleanup_new, 1)
elif 'clearRoomUploadRealtimeForwardHold_(plan.businessDate, plan.site)' not in room:
    raise SystemExit('mirror cleanup anchor not found')

# Make mirror result identify the guarded DB commit path.
first_legacy = room.find('\nfunction applyRoomStatusUpload(')
head, tail = room[:first_legacy], room[first_legacy:]
head = head.replace("uploadRpcVersion: 'V4'", "uploadRpcVersion: 'V5'")
room = head + tail

# 4) Scheduled Sheet->DB forward sync must skip a site while a DB-first upload is awaiting Sheet mirror.
old_rt = """  const rooms = novaRealtimeFinalBuildRooms_(dateText, siteText, '');
  if (!rooms.length) throw new Error(`Realtime 동기화 대상 객실이 없습니다. (${dateText}${siteText ? ' · ' + siteText : ''})`);
  const sites = Array.from(new Set(rooms.map(row => row.site).filter(Boolean))).sort();
  const users = novaRealtimeFinalBuildUsers_(sites);
"""
new_rt = """  let rooms = novaRealtimeFinalBuildRooms_(dateText, siteText, '');
  if (!rooms.length) throw new Error(`Realtime 동기화 대상 객실이 없습니다. (${dateText}${siteText ? ' · ' + siteText : ''})`);
  const heldSites = Array.from(new Set(rooms.map(row => String(row.site || '').trim()).filter(Boolean)))
    .filter(targetSite => typeof isRoomUploadRealtimeForwardHeld_ === 'function' && isRoomUploadRealtimeForwardHeld_(dateText, targetSite));
  if (heldSites.length) {
    rooms = rooms.filter(row => !heldSites.includes(String(row.site || '').trim())); // ROOM_UPLOAD_FORWARD_SYNC_HOLD_V1
  }
  if (!rooms.length) {
    return { ok: true, skipped: true, reason: 'ROOM_UPLOAD_DB_FIRST_MIRROR_PENDING', businessDate: dateText, heldSites };
  }
  const sites = Array.from(new Set(rooms.map(row => row.site).filter(Boolean))).sort();
  const users = novaRealtimeFinalBuildUsers_(sites);
"""
if old_rt in rt:
    rt = rt.replace(old_rt, new_rt, 1)
elif 'ROOM_UPLOAD_DB_FIRST_MIRROR_PENDING' not in rt:
    raise SystemExit('Realtime forward sync anchor not found')

# 5) Client: canonical V5 only; do not fall back to legacy Sheet-first mutation.
client = client.replace("'nova_room_upload_apply_v4'", "'nova_room_upload_apply_v5'", 1)

fallback_pattern = re.compile(r"if \(!businessDate \|\| !site\) \{\s*return callServer\('applyRoomStatusUpload', state\.token, previewId, \{ resetExisting: resetMode \}\);\s*\}")
client, n = fallback_pattern.subn("if (!businessDate || !site) {\n      throw new Error('객실업로드 DB-first 실행에 업무일자와 사업장이 필요합니다.'); // ROOM_UPLOAD_NO_LEGACY_FALLBACK_V1\n    }", client, count=1)
if n == 0 and 'ROOM_UPLOAD_NO_LEGACY_FALLBACK_V1' not in client:
    raise SystemExit('early legacy fallback not found')

legacy_catch = re.compile(r"if \(error\?\.missingRpc \|\| error\?\.code === 'ROOM_UPLOAD_DB_AUTH_UNAVAILABLE'\) \{\s*console\.warn\([^\n]*\);\s*return callServer\('applyRoomStatusUpload', state\.token, previewId, \{ resetExisting: resetMode \}\);\s*\}")
client, n2 = legacy_catch.subn("if (error?.missingRpc || error?.code === 'ROOM_UPLOAD_DB_AUTH_UNAVAILABLE') {\n        throw new Error('객실업로드 DB 안전경로를 사용할 수 없습니다. 데이터 보호를 위해 업로드를 중단합니다.'); // ROOM_UPLOAD_NO_LEGACY_FALLBACK_V1\n      }", client, count=1)
if n2 == 0 and client.count('ROOM_UPLOAD_NO_LEGACY_FALLBACK_V1') < 2:
    raise SystemExit('DB-auth legacy fallback not found')

# Durable mirror recovery uses the existing saved preview/plan and does not re-run the DB mutation.
recovery_helpers = r'''
  // ROOM_UPLOAD_DURABLE_MIRROR_RECOVERY_V1
  const novaRoomUploadMirrorRecoveryRuntime_ = { inFlight: false };
  function novaRoomUploadMirrorRecoveryKey_() { return 'novaRoomUploadMirrorRecoveryV1'; }
  function novaRoomUploadSaveMirrorRecovery_(value) {
    try { localStorage.setItem(novaRoomUploadMirrorRecoveryKey_(), JSON.stringify(Object.assign({ savedAt: Date.now() }, value || {}))); } catch (ignore) {}
  }
  function novaRoomUploadReadMirrorRecovery_() {
    try {
      const parsed = JSON.parse(localStorage.getItem(novaRoomUploadMirrorRecoveryKey_()) || 'null');
      if (!parsed || typeof parsed !== 'object') return null;
      if (Date.now() - Number(parsed.savedAt || 0) > 24 * 60 * 60 * 1000) {
        localStorage.removeItem(novaRoomUploadMirrorRecoveryKey_());
        return null;
      }
      return parsed;
    } catch (ignore) { return null; }
  }
  function novaRoomUploadClearMirrorRecovery_() {
    try { localStorage.removeItem(novaRoomUploadMirrorRecoveryKey_()); } catch (ignore) {}
  }
  async function novaRoomUploadMarkStage_(recovery, stage, errorMessage = '') {
    if (!recovery?.businessDate || !recovery?.site || !recovery?.version || !recovery?.requestId) return null;
    return novaRoomUploadRpcV4_('nova_room_upload_mark_stage_v1', {
      p_business_date: recovery.businessDate,
      p_site: recovery.site,
      p_upload_version: Number(recovery.version || 0),
      p_request_id: recovery.requestId,
      p_stage: stage,
      p_error: String(errorMessage || '').slice(0, 1000)
    });
  }
  async function novaRoomUploadRecoverPendingMirror_(silent = true) {
    const recovery = novaRoomUploadReadMirrorRecovery_();
    if (!recovery || !state.token || novaRoomUploadMirrorRecoveryRuntime_.inFlight) return null;
    if (!recovery.previewId || !recovery.planId || !recovery.businessDate || !recovery.site || !recovery.version) return null;
    novaRoomUploadMirrorRecoveryRuntime_.inFlight = true;
    try {
      const afterState = await novaRoomUploadStateV3_(recovery.businessDate, recovery.site);
      if (!afterState?.ok || Number(afterState.version || 0) < Number(recovery.version || 0)) {
        throw new Error('DB 확정 객실정보가 아직 준비되지 않았습니다.');
      }
      const mirrored = await callServer('mirrorRoomStatusUploadDbFirst', state.token, recovery.previewId, recovery.planId, {
        dbCurrentRows: Array.isArray(afterState.currentRows) ? afterState.currentRows : [],
        version: Number(recovery.version || 0)
      });
      if (!mirrored?.ok) throw new Error(mirrored?.message || 'Sheet 후처리를 완료하지 못했습니다.');
      try { await novaRoomUploadMarkStage_(recovery, 'SHEET_MIRRORED'); } catch (stageError) { console.warn('[NOVA Upload] Sheet stage mark delayed:', stageError); }
      try { await novaRoomUploadMarkStage_(recovery, 'REALTIME_CONVERGED'); } catch (stageError) { console.warn('[NOVA Upload] convergence stage mark delayed:', stageError); }
      novaRoomUploadClearMirrorRecovery_();
      setSyncStatus('객실업로드 DB·Sheet 동기화 복구 완료');
      if (!silent) showToast('객실업로드 후처리 복구가 완료되었습니다.');
      return mirrored;
    } catch (error) {
      if (!silent) showToast(error?.message || '객실업로드 후처리 복구 대기');
      return null;
    } finally {
      novaRoomUploadMirrorRecoveryRuntime_.inFlight = false;
    }
  }
  window.setTimeout(() => { void novaRoomUploadRecoverPendingMirror_(true); }, 5000);
  window.setInterval(() => {
    if (novaRoomUploadReadMirrorRecovery_()) void novaRoomUploadRecoverPendingMirror_(true);
  }, 30000);
'''
if 'ROOM_UPLOAD_DURABLE_MIRROR_RECOVERY_V1' not in client:
    anchor = "  async function novaRoomUploadDbFirstV4_(previewId, resetMode) {"
    if anchor not in client:
        raise SystemExit('client DB-first function anchor not found')
    client = client.replace(anchor, recovery_helpers + '\n\n' + anchor, 1)

# Save durable recovery descriptor immediately after DB commit and extend the stale-forward hold.
commit_check = """    if (!committed?.ok || committed?.dbFirst !== true) {
      throw new Error(committed?.message || '객실업로드 DB 확정 결과를 확인하지 못했습니다.');
    }

    let afterState = null;
"""
commit_check_new = """    if (!committed?.ok || committed?.dbFirst !== true) {
      throw new Error(committed?.message || '객실업로드 DB 확정 결과를 확인하지 못했습니다.');
    }
    const recovery = {
      previewId,
      planId: prepared.planId,
      businessDate: prepared.businessDate,
      site: prepared.site,
      version: Number(committed.version || 0),
      requestId: stable.requestId,
      resetMode: Boolean(resetMode)
    };
    novaRoomUploadSaveMirrorRecovery_(recovery); // ROOM_UPLOAD_DURABLE_MIRROR_RECOVERY_V1
    try {
      await callServer('markRoomUploadDbCommittedHold', state.token, recovery);
    } catch (holdError) {
      console.warn('[NOVA Upload] DB 확정 후 stale-forward 보호 연장 지연:', holdError);
    }

    let afterState = null;
"""
if commit_check in client:
    client = client.replace(commit_check, commit_check_new, 1)
elif 'novaRoomUploadSaveMirrorRecovery_(recovery)' not in client:
    raise SystemExit('client commit check anchor not found')

# DB committed is success; never tell the operator to upload the file again.
client = client.replace(
    "DB 반영은 완료되었으나 최신 객실값을 다시 읽지 못했습니다. 같은 업로드 버튼을 다시 누르면 동일 요청으로 복구를 시도합니다.",
    "DB 반영은 완료되었습니다. 후처리를 자동 복구 중입니다. 재업로드하지 마세요."
)
client = client.replace(
    "DB 반영은 완료되었으나 기존 Sheet 이력 동기화가 지연되었습니다. 같은 업로드 버튼을 다시 눌러 복구해 주세요.",
    "DB 반영은 완료되었습니다. Sheet 후처리를 자동 복구 중입니다. 재업로드하지 마세요."
)

# Trigger recovery shortly after either post-commit failure.
pending_throw = "      error.code = 'ROOM_UPLOAD_DB_COMMITTED_MIRROR_PENDING';\n      throw error;"
if client.count(pending_throw) >= 2:
    client = client.replace(pending_throw, "      error.code = 'ROOM_UPLOAD_DB_COMMITTED_MIRROR_PENDING';\n      window.setTimeout(() => { void novaRoomUploadRecoverPendingMirror_(true); }, 5000);\n      throw error;", 2)
elif client.count('novaRoomUploadRecoverPendingMirror_(true);') < 3:
    raise SystemExit('post-commit failure anchors not found')

# Mark durable stages and clear recovery after the normal mirror path succeeds.
normal_success = """    try { sessionStorage.removeItem(stable.key); } catch (ignore) {}
    return Object.assign({}, mirrored, {
"""
normal_success_new = """    try { await novaRoomUploadMarkStage_(recovery, 'SHEET_MIRRORED'); } catch (stageError) { console.warn('[NOVA Upload] Sheet stage mark delayed:', stageError); }
    try { await novaRoomUploadMarkStage_(recovery, 'REALTIME_CONVERGED'); } catch (stageError) { console.warn('[NOVA Upload] convergence stage mark delayed:', stageError); }
    novaRoomUploadClearMirrorRecovery_();
    try { sessionStorage.removeItem(stable.key); } catch (ignore) {}
    return Object.assign({}, mirrored, {
"""
if normal_success in client:
    client = client.replace(normal_success, normal_success_new, 1)
elif "novaRoomUploadMarkStage_(recovery, 'SHEET_MIRRORED')" not in client:
    raise SystemExit('normal mirror success anchor not found')

# UI: DB-committed/pending means mutation succeeded; disable apply actions and make the status unmistakable.
old_catch = """      if (otherButton) otherButton.disabled = false;
      if ($('uploadPerformanceStatus')) {
        $('uploadPerformanceStatus').textContent = `객실현황 반영 오류 · ${error?.message || '서버 처리 오류'}`;
      }
      showToast(error?.message || '객실현황 반영 오류');
"""
new_catch = """      const dbCommittedPending = String(error?.code || '') === 'ROOM_UPLOAD_DB_COMMITTED_MIRROR_PENDING';
      if (otherButton) otherButton.disabled = dbCommittedPending;
      if (dbCommittedPending) {
        if (button) {
          button.disabled = true;
          button.textContent = 'DB 반영 완료 · 자동복구 중';
        }
        if ($('uploadPerformanceStatus')) $('uploadPerformanceStatus').textContent = `DB 반영 완료 · 후처리 자동복구 중 · 재업로드 금지`;
        setSyncStatus('객실업로드 DB 반영 완료 · 후처리 자동복구 중 · 재업로드 금지');
        window.setTimeout(() => { void novaRoomUploadRecoverPendingMirror_(false); }, 5000);
        showToast(error?.message || 'DB 반영 완료 · 후처리 자동복구 중');
        return;
      }
      if (otherButton) otherButton.disabled = false;
      if ($('uploadPerformanceStatus')) {
        $('uploadPerformanceStatus').textContent = `객실현황 반영 오류 · ${error?.message || '서버 처리 오류'}`;
      }
      showToast(error?.message || '객실현황 반영 오류');
"""
if old_catch in client:
    client = client.replace(old_catch, new_catch, 1)
elif '후처리 자동복구 중 · 재업로드 금지' not in client:
    raise SystemExit('upload UI catch anchor not found')

room_path.write_text(room, encoding='utf-8')
client_path.write_text(client, encoding='utf-8')
rt_path.write_text(rt, encoding='utf-8')

print('ROOM_UPLOAD_RELIABILITY_V5 patch applied')
