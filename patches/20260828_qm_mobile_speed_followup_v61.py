from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'
QM = ROOT / '16_QmChecklist.js'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# Client — incremental follow-up on already deployed v60.
# Preserve START -> immediate checklist modal. Only reduce final/autosave work,
# simplify QM checklist guide, and keep QM cleaner-name display scoped to QM.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')

# Final completion: cancel a pending autosave timer and pass the known draft row.
start = client.find("  async function submitQmInspectionFinal_(event)")
end = client.find("\n  function ", start + 10)
if start < 0 or end < 0:
    fail('QM final submit function not found')
segment = client[start:end]
old = """      // 최종제출 payload 자체에 현재 answers/defects가 모두 포함되므로\n      // 완료 직전 별도 임시저장 RPC를 반복하지 않는다.\n      const result = await callServer('submitQmChecklistInspection', state.token, {\n        businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo: active.roomNo,\n        draftId: active.draft.draftId, revision: active.checklist.revision,\n"""
new = """      // 최종제출 payload 자체에 현재 answers/defects가 모두 포함되므로\n      // 완료 직전 별도 임시저장 RPC를 반복하지 않는다. 대기 중 자동저장도 취소한다.\n      if (state.qmChecklist.autosaveTimer) window.clearTimeout(state.qmChecklist.autosaveTimer);\n      state.qmChecklist.autosaveTimer = null;\n      const result = await callServer('submitQmChecklistInspection', state.token, {\n        businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo: active.roomNo,\n        draftId: active.draft.draftId, draftRowNumber: Number(active.draft.rowNumber || 0), revision: active.checklist.revision,\n"""
segment = replace_once(segment, old, new, 'QM final pending autosave/direct-row payload')
client = client[:start] + segment + client[end:]

# Normal autosave: pass the physical row returned at start/reload.
old = """      const result = await callServer('saveQmInspectionDraft', state.token, { draftId: draft.draftId, answers: draft.answers, defects: draft.defects });\n"""
new = """      const result = await callServer('saveQmInspectionDraft', state.token, { draftId: draft.draftId, draftRowNumber: Number(draft.rowNumber || 0), answers: draft.answers, defects: draft.defects });\n"""
client = replace_once(client, old, new, 'QM autosave direct-row payload')

# Make the checklist guidance shorter and easier to scan; controls/validation stay unchanged.
old = """        <div class=\"qm-checklist-guide\"><b>실시간 저장</b> · 장소별로 양호/불량을 선택하고, 하자는 사진과 함께 등록할 수 있습니다. 최종 저장 시 지적이 있으면 재정비로 전환됩니다.<span id=\"qmDraftSaveStatus\">${escapeHtml(draft.savedAt ? `마지막 저장 ${draft.savedAt}` : '저장 대기')}</span></div>\n"""
new = """        <div class=\"qm-checklist-guide\"><b>점검</b> · 양호/불량을 선택하세요. 불량은 내용을 입력하고, 사진 필수 항목만 사진을 등록하세요.<span id=\"qmDraftSaveStatus\">${escapeHtml(draft.savedAt ? `마지막 저장 ${draft.savedAt}` : '저장 대기')}</span></div>\n"""
client = replace_once(client, old, new, 'QM checklist guide simplification')
CLIENT.write_text(client, encoding='utf-8')


# -----------------------------------------------------------------------------
# Server — direct draft-row validation. Authorization and record-id checks remain
# authoritative. If the row hint is absent/stale, fall back to recent then full
# historical search, preserving compatibility with already-open inspections.
# -----------------------------------------------------------------------------
qm = QM.read_text(encoding='utf-8')

old = """function buildQmDraftResponse_(draftInfo, detail) { // (클라이언트용 점검 초안)\n  return {\n    draftId: String(draftInfo.data['기록ID'] || '').trim(),\n    businessDate: String(draftInfo.data['업무일자'] || '').trim(),\n"""
new = """function buildQmDraftResponse_(draftInfo, detail) { // (클라이언트용 점검 초안)\n  return {\n    draftId: String(draftInfo.data['기록ID'] || '').trim(),\n    rowNumber: Number(draftInfo.rowNumber || 0),\n    businessDate: String(draftInfo.data['업무일자'] || '').trim(),\n"""
qm = replace_once(qm, old, new, 'QM draft response rowNumber')

old = """function getQmInspectionRecordById_(recordId) { // (점검기록 ID 조회)\n  if (!recordId) throw new Error('점검기록 ID가 없습니다.');\n  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n  const headerMap = getHeaderMap_(sheet);\n  const idColumn = headerMap['기록ID'];\n  if (!idColumn) throw new Error('업무이력 기록ID 열이 없습니다.');\n  const match = sheet.getRange(2, idColumn, Math.max(0, sheet.getLastRow() - 1), 1).createTextFinder(recordId).matchEntireCell(true).findNext();\n  if (!match) throw new Error('QM 점검기록을 찾을 수 없습니다.');\n  const rowNumber = match.getRow();\n  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];\n  return { rowNumber, data: rowObjectFromValues_(row, headerMap) };\n}\n"""
new = """function getQmInspectionRecordById_(recordId, preferredRowNumber) { // (점검기록 ID 고속조회·직접행 검증)\n  if (!recordId) throw new Error('점검기록 ID가 없습니다.');\n  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n  const headerMap = getHeaderMap_(sheet);\n  const idColumn = headerMap['기록ID'];\n  if (!idColumn) throw new Error('업무이력 기록ID 열이 없습니다.');\n  const lastRow = sheet.getLastRow();\n  if (lastRow < 2) throw new Error('QM 점검기록을 찾을 수 없습니다.');\n\n  const preferred = Number(preferredRowNumber || 0);\n  if (preferred >= 2 && preferred <= lastRow) {\n    const preferredId = String(sheet.getRange(preferred, idColumn).getDisplayValue() || '').trim();\n    if (preferredId === recordId) {\n      const row = sheet.getRange(preferred, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];\n      return { rowNumber: preferred, data: rowObjectFromValues_(row, headerMap) };\n    }\n  }\n\n  const recentCount = Math.min(NOVA_QM_CHECKLIST.HISTORY_SCAN_ROWS, lastRow - 1);\n  const recentStart = lastRow - recentCount + 1;\n  let match = sheet.getRange(recentStart, idColumn, recentCount, 1)\n    .createTextFinder(recordId).matchEntireCell(true).findNext();\n  if (!match && recentStart > 2) {\n    match = sheet.getRange(2, idColumn, recentStart - 2, 1)\n      .createTextFinder(recordId).matchEntireCell(true).findNext();\n  }\n  if (!match) throw new Error('QM 점검기록을 찾을 수 없습니다.');\n  const rowNumber = match.getRow();\n  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];\n  return { rowNumber, data: rowObjectFromValues_(row, headerMap) };\n}\n"""
qm = replace_once(qm, old, new, 'QM draft fast lookup')

# Autosave: read active checklist outside the global write lock and use the row hint.
save_start = qm.find('function saveQmInspectionDraft(token, payload)')
save_end = qm.find('\nfunction uploadQmInspectionPhoto(', save_start)
if save_start < 0 or save_end < 0:
    fail('saveQmInspectionDraft block not found')
save = qm[save_start:save_end]
old = """    const safe = payload || {};\n    const writeLock = acquireWriteLock_();\n    try {\n      const draftInfo = getQmInspectionRecordById_(String(safe.draftId || '').trim());\n      validateQmDraftOwnership_(draftInfo, user);\n      if (String(draftInfo.data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') throw new Error('이미 완료된 점검입니다.');\n      const detail = parseQmHistoryDetail_(draftInfo.data);\n      const checklist = getQmChecklistForMobile_();\n"""
new = """    const safe = payload || {};\n    const checklist = getQmChecklistForSubmit_();\n    const writeLock = acquireWriteLock_();\n    try {\n      const draftInfo = getQmInspectionRecordById_(String(safe.draftId || '').trim(), safe.draftRowNumber);\n      validateQmDraftOwnership_(draftInfo, user);\n      if (String(draftInfo.data['처리상태'] || '').trim().toUpperCase() !== 'IN_PROGRESS') throw new Error('이미 완료된 점검입니다.');\n      const detail = parseQmHistoryDetail_(draftInfo.data);\n"""
save = replace_once(save, old, new, 'QM autosave short lock/direct row')
qm = qm[:save_start] + save + qm[save_end:]

# Final submit: v60 already moved checklist reads outside the lock; add direct-row lookup.
submit_start = qm.find('function submitQmChecklistInspection(token, payload)')
submit_end = qm.find('\nfunction getQmInspectionAnalytics(', submit_start)
if submit_start < 0 or submit_end < 0:
    fail('submitQmChecklistInspection block not found')
submit = qm[submit_start:submit_end]
old = """      draftInfo = getQmInspectionRecordById_(String(safe.draftId).trim());\n      validateQmDraftOwnership_(draftInfo, user);\n"""
new = """      draftInfo = getQmInspectionRecordById_(String(safe.draftId).trim(), safe.draftRowNumber);\n      validateQmDraftOwnership_(draftInfo, user);\n"""
submit = replace_once(submit, old, new, 'QM final direct-row lookup')
qm = qm[:submit_start] + submit + qm[submit_end:]
QM.write_text(qm, encoding='utf-8')


# -----------------------------------------------------------------------------
# Validation — enforce the four requested boundaries and no unrelated file edits.
# -----------------------------------------------------------------------------
subprocess.run(['node', '--check', str(QM)], cwd=ROOT, check=True)
client_text = CLIENT.read_text(encoding='utf-8')
script_start = client_text.find('<script>')
script_end = client_text.rfind('</script>')
if script_start < 0 or script_end <= script_start:
    fail('Client script block not found')
tmp = ROOT / '.tmp_qm_v61_client.js'
tmp.write_text(client_text[script_start + len('<script>'):script_end], encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(tmp)], cwd=ROOT, check=True)
finally:
    if tmp.exists():
        tmp.unlink()

# 1) Start -> checklist exposure remains exactly ordered before refresh.
start_pos = client_text.find("const result = await callServer('startQmInspection'")
modal_pos = client_text.find('openQmInspectionModal_();', start_pos)
refresh_pos = client_text.find('await loadMobileSnapshot({ silent: true, force: true });', start_pos)
if start_pos < 0 or modal_pos < 0 or refresh_pos < 0 or not (start_pos < modal_pos < refresh_pos):
    fail('QM start/checklist exposure regression guard failed')

# 2) Completion/autosave speed path.
submit_text = client_text[client_text.find('async function submitQmInspectionFinal_'):client_text.find('function renderMobileShell', client_text.find('async function submitQmInspectionFinal_'))]
if 'await saveQmInspectionDraftNow_(false);' in submit_text:
    fail('redundant final draft RPC reintroduced')
if 'draftRowNumber: Number(active.draft.rowNumber || 0)' not in submit_text:
    fail('final draft row hint missing')
qm_check = QM.read_text(encoding='utf-8')
if 'function getQmInspectionRecordById_(recordId, preferredRowNumber)' not in qm_check:
    fail('direct draft-row helper missing')
if "getQmInspectionRecordById_(String(safe.draftId).trim(), safe.draftRowNumber)" not in qm_check:
    fail('final direct draft-row lookup missing')

# 3) Existing v60 QM-only cleaner-name card must remain.
if "role === 'QM' ? (assignedNames || '-') : roomStatus" not in client_text:
    fail('QM cleaner-name display regression')

# 4) Existing scoped large-text UI plus simplified guide must remain.
styles_text = STYLES.read_text(encoding='utf-8') if (ROOT / 'Styles.html').exists() else ''
if 'NOVA v60 — QM 모바일 점검 가독성·미니멀 UI' not in styles_text or 'font-size:17px' not in styles_text:
    fail('QM large-text scoped UI regression')
if '양호/불량을 선택하세요. 불량은 내용을 입력하고' not in client_text:
    fail('QM simplified guide missing')

subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
print('QM_MOBILE_V61_OK')
print('Changed: Client.html, 16_QmChecklist.js only')
print('1) Start -> checklist modal: preserved and regression-guarded')
print('2) Completion: pending autosave cancelled, direct draft-row lookup, shorter autosave lock')
print('3) QM card cleaner-name display: preserved')
print('4) Large/minimal QM checklist UI: preserved; guide text simplified')
print('Syntax/scope: PASS')
