from pathlib import Path
import sys

MARKER = 'QM_DRAFT_DB_FIRST_V1'

bridge = Path('RealtimeBridge.js')
client = Path('Client.html')
bridge_text = bridge.read_text(encoding='utf-8')
client_text = client.read_text(encoding='utf-8')

if MARKER in bridge_text and MARKER in client_text:
    print('QM Draft DB-first V1 already applied.')
    raise SystemExit(0)

# Feature flag is server-side and canary-only. Empty allowlist means OFF even if master flag is Y.
old = "function getNovaRealtimeClientConfig() {"
new = "function getNovaRealtimeClientConfig(token) { // QM_DRAFT_DB_FIRST_V1"
if old not in bridge_text:
    raise SystemExit('RealtimeBridge function anchor not found')
bridge_text = bridge_text.replace(old, new, 1)

old = """  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N')
    .trim()
    .toUpperCase() === 'Y';

  return {
    ok: true,
    enabled: Boolean(enabled && apiBase),
    apiBase: apiBase,
    mode: enabled && apiBase ? 'REALTIME' : 'LEGACY'
  };"""
new = """  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N')
    .trim()
    .toUpperCase() === 'Y';

  let qmDraftDbFirstEnabled = false;
  const qmDraftMasterEnabled = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED') || 'N').trim().toUpperCase() === 'Y';
  const qmDraftEmployees = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES') || '')
    .split(',').map(value => value.trim()).filter(Boolean);
  if (qmDraftMasterEnabled && qmDraftEmployees.length && token) {
    const verified = verifyNovaToken(token);
    const user = verified && verified.ok ? verified.user : null;
    qmDraftDbFirstEnabled = Boolean(user
      && String(user.role || '').trim().toUpperCase() === 'QM'
      && qmDraftEmployees.includes(String(user.employeeNo || '').trim()));
  }

  return {
    ok: true,
    enabled: Boolean(enabled && apiBase),
    apiBase: apiBase,
    mode: enabled && apiBase ? 'REALTIME' : 'LEGACY',
    qmDraftDbFirstEnabled // QM_DRAFT_DB_FIRST_V1
  };"""
if old not in bridge_text:
    raise SystemExit('RealtimeBridge return anchor not found')
bridge_text = bridge_text.replace(old, new, 1)

old = """  if (!props.getProperty('NOVA_REALTIME_API_BASE')) {
    props.setProperty('NOVA_REALTIME_API_BASE', '');
  }
  return {"""
new = """  if (!props.getProperty('NOVA_REALTIME_API_BASE')) {
    props.setProperty('NOVA_REALTIME_API_BASE', '');
  }
  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED', 'N');
  }
  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', '');
  }
  return {"""
if old not in bridge_text:
    raise SystemExit('RealtimeBridge setup anchor not found')
bridge_text = bridge_text.replace(old, new, 1)

# Runtime config state.
old = """    indicatorEventCursorRequestId: '',
    roomStatusProtections: new Map()
  };"""
new = """    indicatorEventCursorRequestId: '',
    roomStatusProtections: new Map(),
    qmDraftDbFirstEnabled: false,
    qmDraftAuthBundle: null
  }; // QM_DRAFT_DB_FIRST_V1"""
if old not in client_text:
    raise SystemExit('Client runtime anchor not found')
client_text = client_text.replace(old, new, 1)

old = """        novaRealtime_.enabled = Boolean(config?.ok && config?.enabled && config?.apiBase);
        novaRealtime_.apiBase = String(config?.apiBase || '').replace(/\\/+$/, '');"""
new = """        novaRealtime_.enabled = Boolean(config?.ok && config?.enabled && config?.apiBase);
        novaRealtime_.apiBase = String(config?.apiBase || '').replace(/\\/+$/, '');
        novaRealtime_.qmDraftDbFirstEnabled = Boolean(config?.qmDraftDbFirstEnabled); // QM_DRAFT_DB_FIRST_V1"""
if old not in client_text:
    raise SystemExit('Client config anchor not found')
client_text = client_text.replace(old, new, 1)

# Add direct PostgREST RPC helper immediately before the existing autosave function.
anchor = "  async function saveQmInspectionDraftNow_(showMessage) { // (점검 초안 서버 저장)"
if anchor not in client_text:
    raise SystemExit('QM autosave function anchor not found')
helper = r'''  let novaQmDraftLegacyMirrorTimer_ = null;

  async function novaQmDraftAuthBundle_() { // QM_DRAFT_DB_FIRST_V1 · Cloud Run이 발급한 Supabase JWT 재사용
    if (novaRealtime_.qmDraftAuthBundle?.token) return novaRealtime_.qmDraftAuthBundle;
    const auth = await novaRealtimeGetAuth_();
    novaRealtime_.qmDraftAuthBundle = auth;
    return auth;
  }

  async function novaQmDraftDbFirstSave_(draft) { // QM_DRAFT_DB_FIRST_V1 · PostgreSQL row-level 저장
    const active = state.qmChecklist.activeInspection;
    if (!active || !draft?.draftId) throw new Error('QM 초안 정보가 없습니다.');
    const auth = await novaQmDraftAuthBundle_();
    const requestId = novaRealtimeRequestId_('QM_DRAFT_SAVE', draft.draftId);
    const expectedVersion = Number(active.draft?.dbVersion || 0);
    const response = await fetch(`${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/nova_save_qm_draft`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': String(auth.publishableKey || ''),
        'Authorization': `Bearer ${auth.token}`
      },
      body: JSON.stringify({
        p_draft_id: String(draft.draftId || ''),
        p_business_date: String(draft.businessDate || active.draft?.businessDate || state.mobile.businessDate || ''),
        p_site: String(draft.site || active.draft?.site || state.mobile.site || ''),
        p_room_no: String(draft.roomNo || active.draft?.roomNo || ''),
        p_checklist_revision: String(active.revision || active.draft?.revision || ''),
        p_answers: Array.isArray(draft.answers) ? draft.answers : [],
        p_defects: Array.isArray(draft.defects) ? draft.defects : [],
        p_expected_version: expectedVersion,
        p_request_id: requestId
      })
    });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = new Error(data?.message || data?.details || `QM DB 자동저장 오류 (${response.status})`);
      error.status = response.status;
      error.code = data?.code || '';
      throw error;
    }
    const row = Array.isArray(data) ? data[0] : data;
    if (!row?.draft_id) throw new Error('QM DB 자동저장 응답을 확인할 수 없습니다.');
    active.draft.dbVersion = Number(row.version || expectedVersion || 0);
    active.draft.dbSavedAt = String(row.saved_at || '');
    return { ok: true, savedAt: active.draft.dbSavedAt, dbVersion: active.draft.dbVersion };
  }

  function novaQmScheduleLegacyDraftMirror_(draft) { // QM_DRAFT_DB_FIRST_V1 · 최종제출/기존 이력 호환용 저빈도 미러
    if (novaQmDraftLegacyMirrorTimer_) window.clearTimeout(novaQmDraftLegacyMirrorTimer_);
    const snapshot = JSON.parse(JSON.stringify({
      draftId: draft.draftId,
      draftRowNumber: Number(draft.rowNumber || 0),
      answers: draft.answers || [],
      defects: draft.defects || []
    }));
    novaQmDraftLegacyMirrorTimer_ = window.setTimeout(() => {
      novaQmDraftLegacyMirrorTimer_ = null;
      callServer('saveQmInspectionDraft', state.token, snapshot).catch(error => {
        console.warn('[NOVA QM] DB-first Sheet 미러 지연 · 최종제출은 기존 경로로 보호됩니다.', error);
      });
    }, 5000);
  }

'''
client_text = client_text.replace(anchor, helper + anchor, 1)

# Replace only the normal autosave call with DB-first + automatic legacy fallback.
old = """      const result = await callServer('saveQmInspectionDraft', state.token, { draftId: draft.draftId, draftRowNumber: Number(draft.rowNumber || 0), answers: draft.answers, defects: draft.defects });
      if (!result?.ok) throw new Error(result?.message || '임시 저장하지 못했습니다.');
      active.draft = Object.assign({}, active.draft, result.draft || {}, { answers: draft.answers, defects: draft.defects });
      if (status) status.textContent = `실시간 저장 ${result.savedAt || ''}`;"""
new = """      let result;
      if (novaRealtime_.qmDraftDbFirstEnabled && novaRealtimeIsEnabled_()) {
        try {
          const dbResult = await novaQmDraftDbFirstSave_(draft);
          result = { ok: true, savedAt: dbResult.savedAt, draft: active.draft, dbFirst: true };
          active.draft = Object.assign({}, active.draft, { answers: draft.answers, defects: draft.defects, dbVersion: dbResult.dbVersion });
          novaQmScheduleLegacyDraftMirror_(Object.assign({}, active.draft, { answers: draft.answers, defects: draft.defects }));
        } catch (dbError) {
          console.warn('[NOVA QM] DB-first 자동저장 실패 · 기존 Sheet 저장으로 즉시 fallback', dbError);
          result = await callServer('saveQmInspectionDraft', state.token, { draftId: draft.draftId, draftRowNumber: Number(draft.rowNumber || 0), answers: draft.answers, defects: draft.defects });
        }
      } else {
        result = await callServer('saveQmInspectionDraft', state.token, { draftId: draft.draftId, draftRowNumber: Number(draft.rowNumber || 0), answers: draft.answers, defects: draft.defects });
      }
      if (!result?.ok) throw new Error(result?.message || '임시 저장하지 못했습니다.');
      active.draft = Object.assign({}, active.draft, result.draft || {}, { answers: draft.answers, defects: draft.defects });
      if (status) status.textContent = `${result.dbFirst ? 'DB 실시간 저장' : '실시간 저장'} ${result.savedAt || ''}`; // QM_DRAFT_DB_FIRST_V1"""
if old not in client_text:
    raise SystemExit('QM autosave call anchor not found')
client_text = client_text.replace(old, new, 1)

# Safety markers: existing final submit and legacy method must remain.
required = [
    "async function submitQmInspectionFinal_",
    "callServer('saveQmInspectionDraft'",
    "novaRealtimeGetAuth_()",
    "QM_DRAFT_DB_FIRST_V1",
]
missing = [x for x in required if x not in client_text]
if missing:
    raise SystemExit('Safety validation failed: ' + ', '.join(missing))

bridge.write_text(bridge_text, encoding='utf-8')
client.write_text(client_text, encoding='utf-8')
print('Applied QM_DRAFT_DB_FIRST_V1 with canary flag and legacy fallback.')
