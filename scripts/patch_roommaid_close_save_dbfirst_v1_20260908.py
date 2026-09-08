from pathlib import Path
import sys

MARKER = 'ROOMMAID_CLOSE_SAVE_DB_FIRST_V1'


def fail(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    raise SystemExit(91)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and new in text:
        return text
    fail(f'{label}: expected 1 anchor, found {count}')


# 1) RPC allowlist.
p = Path('DbFirstBridge.js')
s = p.read_text(encoding='utf-8')
old = "    'nova_daily_close_cancel_many_v1',\n    'nova_monthly_history_v1',"
new = "    'nova_daily_close_cancel_many_v1',\n    'nova_roommaid_close_cancel_v1', // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1\n    'nova_monthly_history_v1',"
s = replace_once(s, old, new, 'roommaid close cancel RPC allowlist')
p.write_text(s, encoding='utf-8')

# 2) Daily-close bridge: legacy upload metadata compatibility only for pre-V4 roommaid-close days.
p = Path('DailyCloseDbFirstBridge.js')
s = p.read_text(encoding='utf-8')
source_anchor = """function novaDailyCloseSourceDbFirst_(token, businessDate, site) {\n  return novaDbFirstRpc_(token, 'nova_daily_close_source_v1', {\n    p_business_date: normalizeBusinessDate_(businessDate),\n    p_site: String(site || '').trim()\n  }, { readOnly: true, allowLegacyFallback: true });\n}\n\n"""
helper = r'''// ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
// V4 이전 업로드로 DB snapshot만 없는 업무일은 DB 현재객실을 유지하고,
// Sheet에서 최종 ROOM_STATUS_UPLOAD 원본 메타데이터 1건만 보강합니다.
function novaDailyCloseLegacyUploadCompatSource_(source, businessDate, site) {
  const safe = source && typeof source === 'object' ? source : {};
  if (safe.ready === true) return safe;
  const reasons = (Array.isArray(safe.reasons) ? safe.reasons : []).map(value => String(value || '').trim()).filter(Boolean);
  const allowedReasons = new Set(['ACTIVE_UPLOAD_SNAPSHOT_MISSING', 'ROOM_COUNT_MISMATCH']);
  if (!reasons.length || reasons.some(reason => !allowedReasons.has(reason))) return safe;

  const metrics = safe.metrics && typeof safe.metrics === 'object' ? safe.metrics : {};
  const roomCount = Number(metrics.rooms || 0);
  if (roomCount <= 0 || Number(metrics.activeUploads || 0) !== 0) return safe;

  const bundle = readRoommaidCloseHistoryBundleFast_(normalizeBusinessDate_(businessDate), String(site || '').trim());
  const uploads = (Array.isArray(bundle && bundle.historyRows) ? bundle.historyRows : [])
    .filter(row => String(row && row['기록구분'] || '').trim() === NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD)
    .filter(row => String(row && row['처리상태'] || '').trim().toUpperCase() === 'APPLIED')
    .filter(row => String(row && row['삭제여부'] || 'N').trim().toUpperCase() !== 'Y')
    .sort((a, b) => Number(b && b['변경버전'] || 0) - Number(a && a['변경버전'] || 0)
      || String(b && b['등록일시'] || '').localeCompare(String(a && a['등록일시'] || '')));
  const upload = uploads[0] || null;
  if (!upload) return safe;

  const detail = parseHistoryDetailSafe_(upload);
  const uploadTotal = Number(detail && detail.totalRooms || 0);
  const roomsByStatus = detail && detail.roomsByStatus && typeof detail.roomsByStatus === 'object' ? detail.roomsByStatus : {};
  if (!uploadTotal || uploadTotal !== roomCount || !Object.keys(roomsByStatus).length) return safe;

  const dbHistory = (Array.isArray(safe.historyRows) ? safe.historyRows : [])
    .filter(row => String(row && row['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.ROOM_STATUS_UPLOAD);
  return Object.assign({}, safe, {
    ready: true,
    reasons: [],
    historyRows: [upload].concat(dbHistory),
    metrics: Object.assign({}, metrics, { activeUploads: 1, uploadTotalRooms: uploadTotal, legacyUploadCompat: true }),
    compatibility: Object.assign({}, safe.compatibility || {}, {
      legacyUploadSnapshot: true,
      uploadVersion: Number(upload['변경버전'] || 0),
      uploadRegisteredAt: String(upload['등록일시'] || '').trim()
    })
  });
}

'''
if MARKER not in s:
    if source_anchor not in s:
        fail('daily close source helper anchor missing')
    s = s.replace(source_anchor, source_anchor + helper, 1)

old = """    candidates.forEach(site => {\n      const source = novaDailyCloseSourceDbFirst_(token, businessDate, site);\n      if (source && source.legacyFallback) {\n"""
new = """    candidates.forEach(site => {\n      const rawSource = novaDailyCloseSourceDbFirst_(token, businessDate, site);\n      const source = safe.roommaidCloseCompat === true\n        ? novaDailyCloseLegacyUploadCompatSource_(rawSource, businessDate, site)\n        : rawSource; // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1\n      if (source && source.legacyFallback) {\n"""
s = replace_once(s, old, new, 'roommaid close source compat routing')

wrapper_anchor = "function buildDailyCloseOverviewDbFirst_(token, request) { // (DB close 우선 + 비전환 과거일만 legacy 보존)\n"
wrappers = r'''function saveRoommaidCloseJournalDbFirst(token, payload) { // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
  return measureResponse_('saveRoommaidCloseJournalDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('마감할 사업장을 선택하세요.');
    const result = saveDailyCloseSnapshotDbFirst(token, {
      businessDate,
      site,
      attendanceEmployeeNos: uniqueEmployeeNos_(safe.attendanceEmployeeNos || []),
      requestId: String(safe.requestId || '').trim(),
      roommaidCloseCompat: true
    });
    if (!result || result.ok !== true) throw new Error(result && result.message || '룸메이드 마감일지를 저장하지 못했습니다.');
    const siteResult = Array.isArray(result.sites)
      ? result.sites.find(item => String(item && item.site || '').trim() === site) || result.sites[0]
      : null;
    const snapshot = siteResult && siteResult.snapshot && typeof siteResult.snapshot === 'object' ? siteResult.snapshot : {};
    return {
      ok: true,
      dbFirst: result.dbFirst === true,
      businessDate,
      site,
      closedAt: String(snapshot.closedAt || siteResult && siteResult.closedAt || '').trim(),
      message: `${businessDate} ${site} 룸메이드 마감일지를 저장했습니다.`
    };
  });
}

function resetRoommaidCloseJournalDbFirst(token, payload) { // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1
  return measureResponse_('resetRoommaidCloseJournalDbFirst', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate || safe.date);
    const site = String(safe.site || '').trim();
    if (!site) throw new Error('초기화할 사업장을 선택하세요.');
    const requestId = String(safe.requestId || novaDbFirstRequestId_(`ROOMMAID_CLOSE_CANCEL_${site}`)).trim();
    const db = novaDbFirstRpc_(token, 'nova_roommaid_close_cancel_v1', {
      p_business_date: businessDate,
      p_site: site,
      p_reason: 'ROOMMAID_CLOSE_RESET',
      p_request_id: requestId
    }, { allowLegacyFallback: true });

    if (db && db.legacyFallback) return resetRoommaidCloseJournal(token, payload);
    if (!db || db.ok !== true) throw new Error(db && db.message || '룸메이드 마감자료를 초기화하지 못했습니다.');
    if (db.noDbSnapshot === true) return resetRoommaidCloseJournal(token, payload);

    let mirror = null;
    try { mirror = resetRoommaidCloseJournal(token, payload); }
    catch (error) { console.warn('[NOVA DB] 룸메이드 마감 DB 취소 후 Sheet 미러 지연:', error && error.message || error); }
    const mirrorOk = Boolean(mirror && mirror.ok === true);
    return {
      ok: true,
      dbFirst: true,
      businessDate,
      site,
      resetCount: Number(mirrorOk ? mirror.resetCount : db.cancelledCount || 1),
      resetBy: String(db.cancelledBy || '').trim(),
      resetAt: nowText_(),
      sheetMirrorPending: !mirrorOk,
      message: `${businessDate} ${site} 룸메이드 마감자료를 초기화했습니다. 현재 자료를 확인한 후 다시 마감하세요.`
    };
  });
}

'''
if 'function saveRoommaidCloseJournalDbFirst(' not in s:
    if wrapper_anchor not in s:
        fail('daily close wrapper anchor missing')
    s = s.replace(wrapper_anchor, wrappers + wrapper_anchor, 1)
p.write_text(s, encoding='utf-8')

# 3) Client buttons only; UI/labels remain unchanged.
p = Path('Client.html')
s = p.read_text(encoding='utf-8')
s = replace_once(s,
    "const result = await callServer('saveRoommaidCloseJournal', state.token, {",
    "const result = await callServer('saveRoommaidCloseJournalDbFirst', state.token, { // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1",
    'roommaid close save client route')
s = replace_once(s,
    "const result = await callServer('resetRoommaidCloseJournal', state.token, {",
    "const result = await callServer('resetRoommaidCloseJournalDbFirst', state.token, { // ROOMMAID_CLOSE_SAVE_DB_FIRST_V1",
    'roommaid close reset client route')
p.write_text(s, encoding='utf-8')

# 4) Whole-DB regression gate.
p = Path('scripts/validate_whole_db_transition_v2_20260908.py')
s = p.read_text(encoding='utf-8')
s = replace_once(s,
    "delay_sql = read('supabase/migrations/20260907_departure_delay_db_first_v3.sql')\n",
    "delay_sql = read('supabase/migrations/20260907_departure_delay_db_first_v3.sql')\nroommaid_close_cancel_sql = read('supabase/migrations/20260908_roommaid_close_cancel_db_first_v1.sql')\n",
    'validator migration source')
s = replace_once(s,
    "    'nova_daily_close_save_v2', 'nova_daily_close_read_v1',\n    'nova_monthly_history_v1',",
    "    'nova_daily_close_save_v2', 'nova_daily_close_read_v1', 'nova_roommaid_close_cancel_v1',\n    'nova_monthly_history_v1',",
    'validator RPC allowlist')
anchor = "require(client, \"novaRealtimeRequestId_('DAILY_CLOSE_V3'\", 'daily-close request id')\n"
checks = """require(client, \"novaRealtimeRequestId_('DAILY_CLOSE_V3'\", 'daily-close request id')\nrequire(daily, 'ROOMMAID_CLOSE_SAVE_DB_FIRST_V1', 'roommaid close DB-first marker')\nrequire(daily, 'novaDailyCloseLegacyUploadCompatSource_', 'pre-V4 upload metadata compatibility')\nrequire(daily, 'function saveRoommaidCloseJournalDbFirst(', 'roommaid close DB-first save wrapper')\nrequire(daily, 'function resetRoommaidCloseJournalDbFirst(', 'roommaid close DB-first reset wrapper')\nrequire(daily, \"'nova_roommaid_close_cancel_v1'\", 'roommaid close cancel RPC')\nrequire(client, \"callServer('saveRoommaidCloseJournalDbFirst'\", 'roommaid close save DB route')\nrequire(client, \"callServer('resetRoommaidCloseJournalDbFirst'\", 'roommaid close reset DB route')\nforbid(client, \"callServer('saveRoommaidCloseJournal', state.token\", 'roommaid close direct Sheet save removed')\nforbid(client, \"callServer('resetRoommaidCloseJournal', state.token\", 'roommaid close direct Sheet reset removed')\nrequire(close, 'function saveRoommaidCloseJournal(', 'legacy roommaid close writer preserved')\nrequire(close, 'function resetRoommaidCloseJournal(', 'legacy roommaid reset writer preserved')\nrequire(roommaid_close_cancel_sql, 'NOVA_ROOMMAID_CLOSE_CANCEL_DB_FIRST_V1', 'roommaid close cancel migration marker')\nrequire(roommaid_close_cancel_sql, \"not in ('ADMIN', 'ORDER')\", 'roommaid close reset role parity')\nrequire(roommaid_close_cancel_sql, 'revoke all on function public.nova_roommaid_close_cancel_v1', 'roommaid close cancel default execute revoked')\n"""
s = replace_once(s, anchor, checks, 'validator roommaid close checks')
s = replace_once(s,
    "    'patch_roommaid_reporting_dbfirst_v2_20260907.py',\n    'validate_whole_db_transition_v2_20260908.py'",
    "    'patch_roommaid_reporting_dbfirst_v2_20260907.py',\n    'patch_roommaid_close_save_dbfirst_v1_20260908.py',\n    'validate_whole_db_transition_v2_20260908.py'",
    'validator canonical patch list')
s = replace_once(s,
    "    'scripts/patch_roommaid_reporting_dbfirst_v2_20260907.py'\n]:",
    "    'scripts/patch_roommaid_reporting_dbfirst_v2_20260907.py',\n    'scripts/patch_roommaid_close_save_dbfirst_v1_20260908.py'\n]:",
    'validator idempotence patch list')
p.write_text(s, encoding='utf-8')

# 5) Canonical meta-patcher owns the new patch on every deployment.
p = Path('scripts/fix_patch_site_scope_v2.py')
s = p.read_text(encoding='utf-8')
old = "subprocess.run([sys.executable, 'scripts/patch_roommaid_reporting_dbfirst_v2_20260907.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/validate_whole_db_transition_v2_20260908.py'], check=True)"
new = "subprocess.run([sys.executable, 'scripts/patch_roommaid_reporting_dbfirst_v2_20260907.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/patch_roommaid_close_save_dbfirst_v1_20260908.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/validate_whole_db_transition_v2_20260908.py'], check=True)"
s = replace_once(s, old, new, 'canonical roommaid close patch registration')
p.write_text(s, encoding='utf-8')

print('Roommaid close save/reset DB-first patch applied.')
