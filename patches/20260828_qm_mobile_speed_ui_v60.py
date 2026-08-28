from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'Client.html'
QM = ROOT / '16_QmChecklist.js'
STYLES = ROOT / 'Styles.html'


def fail(message):
    raise SystemExit(f'PATCH_ERROR: {message}')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        fail(f'{label}: expected 1 match, found {count}')
    return text.replace(old, new, 1)


def replace_exact_count(text, old, new, expected, label):
    count = text.count(old)
    if count != expected:
        fail(f'{label}: expected {expected} matches, found {count}')
    return text.replace(old, new)


# -----------------------------------------------------------------------------
# 1) Client — preserve the existing START -> checklist modal flow, accelerate
#    final submit, show cleaner name on QM cards, and simplify checklist wording.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')

# Final submit already includes all current answers/defects. Do not perform a
# second draft-save RPC immediately before it, and pass the known draft row so
# the server can verify one row instead of searching the whole history sheet.
start = client.find("  async function submitQmInspectionFinal_(event)")
end = client.find("\n  function ", start + 10)
if start < 0 or end < 0:
    fail('QM final submit function not found')
segment = client[start:end]
old = """    try {\n      await saveQmInspectionDraftNow_(false);\n      const result = await callServer('submitQmChecklistInspection', state.token, {\n"""
new = """    try {\n      // 최종제출 payload 자체에 현재 answers/defects가 모두 포함되므로\n      // 완료 직전 별도 임시저장 RPC를 반복하지 않는다.\n      if (state.qmChecklist.autosaveTimer) window.clearTimeout(state.qmChecklist.autosaveTimer);\n      state.qmChecklist.autosaveTimer = null;\n      const result = await callServer('submitQmChecklistInspection', state.token, {\n"""
segment = replace_once(segment, old, new, 'remove redundant QM draft save before final submit')
old = """        businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo: active.roomNo,\n        draftId: active.draft.draftId, revision: active.checklist.revision,\n"""
new = """        businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo: active.roomNo,\n        draftId: active.draft.draftId, draftRowNumber: Number(active.draft.rowNumber || 0), revision: active.checklist.revision,\n"""
segment = replace_once(segment, old, new, 'QM final direct draft row')
old = """      showToast(result.message || '점검결과를 저장했습니다.');\n      await loadMobileSnapshot({ silent: true, force: true });\n"""
new = """      showToast(result.message || '점검결과를 저장했습니다.');\n      // 완료 성공 응답을 먼저 사용자에게 돌려주고, 카드 최신화는 뒤에서 수행한다.\n      loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 완료 후 화면갱신 실패:', error));\n"""
segment = replace_once(segment, old, new, 'nonblocking QM post-submit refresh')
client = client[:start] + segment + client[end:]

# Autosave and modal-close save also pass the known draft row. The server still
# validates recordId/ownership before writing, so this is only an index shortcut.
old = """      const result = await callServer('saveQmInspectionDraft', state.token, { draftId: draft.draftId, answers: draft.answers, defects: draft.defects });\n"""
new = """      const result = await callServer('saveQmInspectionDraft', state.token, { draftId: draft.draftId, draftRowNumber: Number(draft.rowNumber || 0), answers: draft.answers, defects: draft.defects });\n"""
client = replace_once(client, old, new, 'QM autosave direct draft row')
old = """      callServer('saveQmInspectionDraft', state.token, {\n        draftId: draft.draftId,\n        answers: draft.answers || [],\n        defects: draft.defects || []\n      }).then(result => {\n"""
new = """      callServer('saveQmInspectionDraft', state.token, {\n        draftId: draft.draftId,\n        draftRowNumber: Number(draft.rowNumber || 0),\n        answers: draft.answers || [],\n        defects: draft.defects || []\n      }).then(result => {\n"""
client = replace_once(client, old, new, 'QM close-modal direct draft row')

# QM card: replace the room-status word (퇴실/재고 등) with the actual cleaner
# name(s). Other roles retain their existing room-status display unchanged.
old = """      <div class=\"mobile-room-status\"><b>${escapeHtml(roomStatus)}</b><span>${escapeHtml(cleaningStatus)}</span></div>\n"""
new = """      <div class=\"mobile-room-status${role === 'QM' ? ' qm-assignee-status' : ''}\"><b>${escapeHtml(role === 'QM' ? (assignedNames || '정비자 미지정') : roomStatus)}</b><span>${escapeHtml(cleaningStatus)}</span></div>\n"""
client = replace_once(client, old, new, 'QM room card cleaner name')

# Shorter checklist guide; all functional controls and validation remain intact.
old = """        <div class=\"qm-checklist-guide\"><b>실시간 저장</b> · 장소별로 양호/불량을 선택하고, 하자는 사진과 함께 등록할 수 있습니다. 최종 저장 시 지적이 있으면 재정비로 전환됩니다.<span id=\"qmDraftSaveStatus\">${escapeHtml(draft.savedAt ? `마지막 저장 ${draft.savedAt}` : '저장 대기')}</span></div>\n"""
new = """        <div class=\"qm-checklist-guide\"><b>점검</b> · 양호/불량을 선택하세요. 불량은 내용을 입력하고, 사진 필수 항목은 사진을 등록하세요.<span id=\"qmDraftSaveStatus\">${escapeHtml(draft.savedAt ? `마지막 저장 ${draft.savedAt}` : '저장 대기')}</span></div>\n"""
client = replace_once(client, old, new, 'QM checklist guide simplification')
CLIENT.write_text(client, encoding='utf-8')


# -----------------------------------------------------------------------------
# 2) Server — keep all existing permission/state/history semantics. Optimize only
#    QM draft lookup and final-submit read/response work.
# -----------------------------------------------------------------------------
qm = QM.read_text(encoding='utf-8')

# Include the physical draft row in the client response. Rows are append-only in
# normal operation; every direct-row lookup still verifies the recordId.
old = """  return {\n    draftId: String(draftInfo.data['기록ID'] || '').trim(),\n    businessDate: String(draftInfo.data['업무일자'] || '').trim(),\n"""
new = """  return {\n    draftId: String(draftInfo.data['기록ID'] || '').trim(),\n    rowNumber: Number(draftInfo.rowNumber || 0),\n    businessDate: String(draftInfo.data['업무일자'] || '').trim(),\n"""
qm = replace_once(qm, old, new, 'QM draft response row number')

# Fast lookup: preferred row -> recent tail window -> historical fallback.
old = """function getQmInspectionRecordById_(recordId) { // (점검기록 ID 조회)\n  if (!recordId) throw new Error('점검기록 ID가 없습니다.');\n  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n  const headerMap = getHeaderMap_(sheet);\n  const idColumn = headerMap['기록ID'];\n  if (!idColumn) throw new Error('업무이력 기록ID 열이 없습니다.');\n  const match = sheet.getRange(2, idColumn, Math.max(0, sheet.getLastRow() - 1), 1).createTextFinder(recordId).matchEntireCell(true).findNext();\n  if (!match) throw new Error('QM 점검기록을 찾을 수 없습니다.');\n  const rowNumber = match.getRow();\n  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];\n  return { rowNumber, data: rowObjectFromValues_(row, headerMap) };\n}\n"""
new = """function getQmInspectionRecordById_(recordId, preferredRowNumber) { // (점검기록 ID 고속조회·직접행 검증)\n  if (!recordId) throw new Error('점검기록 ID가 없습니다.');\n  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);\n  const headerMap = getHeaderMap_(sheet);\n  const idColumn = headerMap['기록ID'];\n  if (!idColumn) throw new Error('업무이력 기록ID 열이 없습니다.');\n  const lastRow = sheet.getLastRow();\n  if (lastRow < 2) throw new Error('QM 점검기록을 찾을 수 없습니다.');\n\n  const preferred = Number(preferredRowNumber || 0);\n  if (preferred >= 2 && preferred <= lastRow) {\n    const preferredId = String(sheet.getRange(preferred, idColumn).getDisplayValue() || '').trim();\n    if (preferredId === recordId) {\n      const row = sheet.getRange(preferred, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];\n      return { rowNumber: preferred, data: rowObjectFromValues_(row, headerMap) };\n    }\n  }\n\n  const recentCount = Math.min(NOVA_QM_CHECKLIST.HISTORY_SCAN_ROWS, lastRow - 1);\n  const recentStart = lastRow - recentCount + 1;\n  let match = sheet.getRange(recentStart, idColumn, recentCount, 1)\n    .createTextFinder(recordId).matchEntireCell(true).findNext();\n  if (!match && recentStart > 2) {\n    match = sheet.getRange(2, idColumn, recentStart - 2, 1)\n      .createTextFinder(recordId).matchEntireCell(true).findNext();\n  }\n  if (!match) throw new Error('QM 점검기록을 찾을 수 없습니다.');\n  const rowNumber = match.getRow();\n  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];\n  return { rowNumber, data: rowObjectFromValues_(row, headerMap) };\n}\n"""
qm = replace_once(qm, old, new, 'QM draft fast lookup')

# Autosave direct row.
old = """      const draftInfo = getQmInspectionRecordById_(String(safe.draftId || '').trim());\n      validateQmDraftOwnership_(draftInfo, user);\n"""
new = """      const draftInfo = getQmInspectionRecordById_(String(safe.draftId || '').trim(), safe.draftRowNumber);\n      validateQmDraftOwnership_(draftInfo, user);\n"""
qm = replace_once(qm, old, new, 'QM autosave direct server row')

# Final submit: read-only checklist work stays outside the global write lock and
# uses one code-table read instead of seed/migration/read cycles.
submit_start = qm.find('function submitQmChecklistInspection(token, payload)')
submit_end = qm.find('\nfunction getQmInspectionAnalytics(', submit_start)
if submit_start < 0 or submit_end < 0:
    fail('submitQmChecklistInspection block not found')
submit = qm[submit_start:submit_end]
old = """    const writeLock = acquireWriteLock_();\n    try {\n\n    const checklist = getQmChecklistForMobile_();\n    if (!checklist.items.length) throw new Error('사용 중인 QM 체크리스트가 없습니다. 관리자 또는 오더테이커가 체크리스트를 등록해야 합니다.');\n    if (safe.revision && String(safe.revision) !== checklist.revision) throw new Error('체크리스트가 변경되었습니다. 화면을 새로고침한 뒤 다시 작성하세요.');\n\n"""
new = """    // 체크리스트 조회는 읽기 작업이므로 전역 쓰기잠금 밖에서 처리한다.\n    // 점검완료의 잠금 대기시간을 줄이고 다른 객실 작업을 불필요하게 막지 않는다.\n    const checklist = getQmChecklistForSubmit_();\n    if (!checklist.items.length) throw new Error('사용 중인 QM 체크리스트가 없습니다. 관리자 또는 오더테이커가 체크리스트를 등록해야 합니다.');\n    if (safe.revision && String(safe.revision) !== checklist.revision) throw new Error('체크리스트가 변경되었습니다. 화면을 새로고침한 뒤 다시 작성하세요.');\n\n    const writeLock = acquireWriteLock_();\n    try {\n\n"""
submit = replace_once(submit, old, new, 'move QM checklist read before lock')
old = """      draftInfo = getQmInspectionRecordById_(String(safe.draftId).trim());\n      validateQmDraftOwnership_(draftInfo, user);\n"""
new = """      draftInfo = getQmInspectionRecordById_(String(safe.draftId).trim(), safe.draftRowNumber);\n      validateQmDraftOwnership_(draftInfo, user);\n"""
submit = replace_once(submit, old, new, 'QM final direct server row')

# Avoid loading the complete user index solely to compose the success response.
# The client refreshes its snapshot asynchronously after successful save.
old = """      room: currentRoomObject_(refreshed, rowInfo.rowNumber, {}, getUserIndex_().byEmployeeNo),\n"""
new = """      room: {\n        businessDate,\n        site: String(rowInfo.data['사업장'] || site).trim(),\n        roomNo,\n        roomStatus: String(rowInfo.data['객실상태'] || '').trim(),\n        cleaningStatus: String(updates['청소상태'] || '').trim(),\n        roommaidEmployeeNo: roommaidNo,\n        secondaryRoommaidEmployeeNo: secondaryRoommaidNo,\n        qmEmployeeNo: user.employeeNo,\n        version\n      },\n"""
submit = replace_once(submit, old, new, 'lightweight QM final response room')
qm = qm[:submit_start] + submit + qm[submit_end:]

anchor = "function getQmChecklistForMobile_() { // (QM 모바일 장소별 체크리스트 조회)\n"
if anchor not in qm:
    fail('getQmChecklistForMobile anchor not found')
helper = r"""
function getQmChecklistForSubmit_() { // (QM 최종제출용 읽기전용 체크리스트 고속조회)
  const rows = readAllCodeRows_();
  const places = rows
    .filter(row => row.group === NOVA_QM_CHECKLIST.PLACE_GROUP && row.enabled === 'Y')
    .map(row => ({ code: row.code, label: row.label, order: Number(row.order || 9999) }))
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'ko'));
  const placeMap = {};
  places.forEach(place => { placeMap[place.code] = place; });
  const items = rows
    .filter(row => row.group === NOVA_QM_CHECKLIST.GROUP && row.enabled === 'Y')
    .map(row => qmChecklistItemFromCodeRow_(row, placeMap))
    .sort((a, b) => a.placeOrder - b.placeOrder || a.order - b.order || a.label.localeCompare(b.label, 'ko'));
  return {
    places,
    items,
    groups: places.map(place => ({ place, items: items.filter(item => item.placeCode === place.code) })).filter(group => group.items.length),
    revision: buildQmChecklistRevision_(items, places),
    maxPhotosPerTarget: NOVA_QM_CHECKLIST.MAX_PHOTOS_PER_TARGET
  };
}

"""
if 'function getQmChecklistForSubmit_()' not in qm:
    qm = qm.replace(anchor, helper + anchor, 1)
QM.write_text(qm, encoding='utf-8')


# -----------------------------------------------------------------------------
# 3) QM checklist UI only — larger text/touch targets and flatter, simpler
#    surfaces. No global component or non-QM mobile style changes.
# -----------------------------------------------------------------------------
styles = STYLES.read_text(encoding='utf-8')
css = r"""

/* NOVA v60 — QM 모바일 점검 가독성·미니멀 UI */
.qm-checklist-modal.rc3 .modal-header h2{font-size:20px;line-height:1.3}
.qm-checklist-modal.rc3 .modal-header p{font-size:14px;line-height:1.45}
.qm-checklist-modal.rc3 .qm-checklist-guide{padding:10px 2px;margin-bottom:8px;background:#fff;border-radius:0;font-size:14px;line-height:1.55}
.qm-checklist-modal.rc3 .qm-checklist-guide>span{font-size:13px;color:#6b7280}
.qm-checklist-modal.rc3 .qm-checklist-place-list{gap:6px}
.qm-checklist-modal.rc3 .qm-inspection-place{background:#fff;border-radius:8px}
.qm-checklist-modal.rc3 .qm-inspection-place>summary{padding:15px 12px}
.qm-checklist-modal.rc3 .qm-inspection-place>summary strong{font-size:18px;line-height:1.35}
.qm-checklist-modal.rc3 .qm-inspection-place>summary span{font-size:13px;font-weight:700}
.qm-checklist-modal.rc3 .qm-place-items,.qm-checklist-modal.rc3 .qm-custom-defects{gap:8px;padding:6px 10px 12px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item.rc3{grid-template-columns:1fr;gap:10px;padding:14px 10px;border-radius:7px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-heading{gap:7px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-heading strong{font-size:17px;line-height:1.5}
.qm-checklist-modal.rc3 .qm-checklist-inspection-heading span{font-size:12px;padding:4px 7px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item label,.qm-checklist-modal.rc3 .qm-custom-defect label{font-size:14px;gap:7px;font-weight:700;color:#475569}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item select,.qm-checklist-modal.rc3 .qm-checklist-inspection-item textarea,.qm-checklist-modal.rc3 .qm-checklist-inspection-item input,.qm-checklist-modal.rc3 .qm-custom-defect textarea{font-size:17px;min-height:50px;padding:11px 12px;border-radius:7px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item textarea,.qm-checklist-modal.rc3 .qm-custom-defect textarea{min-height:78px;line-height:1.55}
.qm-checklist-modal.rc3 .qm-photo-control{gap:8px}
.qm-checklist-modal.rc3 .qm-add-defect{min-height:48px;font-size:15px}
.qm-checklist-modal.rc3 .modal-actions.sticky{gap:8px;padding-top:10px}
.qm-checklist-modal.rc3 .modal-actions.sticky button{min-height:54px;font-size:16px;font-weight:800}
.mobile-room-status.qm-assignee-status b{font-size:16px;line-height:1.35}
@media(max-width:760px){
  .qm-checklist-modal.rc3{width:calc(100vw - 6px);max-height:calc(100vh - 6px)}
  .qm-checklist-modal.rc3 .modal-body{padding-left:10px;padding-right:10px}
  .qm-checklist-modal.rc3 .qm-inspection-place>summary{align-items:center}
  .qm-checklist-modal.rc3 .qm-photo-control label{font-size:14px}
}
"""
if 'NOVA v60 — QM 모바일 점검 가독성·미니멀 UI' not in styles:
    pos = styles.rfind('</style>')
    if pos < 0:
        fail('Styles closing tag not found')
    styles = styles[:pos] + css + '\n' + styles[pos:]
STYLES.write_text(styles, encoding='utf-8')


# -----------------------------------------------------------------------------
# Validation — requested scope only.
# -----------------------------------------------------------------------------
subprocess.run(['node', '--check', str(QM)], cwd=ROOT, check=True)

client_text = CLIENT.read_text(encoding='utf-8')
script_start = client_text.find('<script>')
script_end = client_text.rfind('</script>')
if script_start < 0 or script_end <= script_start:
    fail('Client script block not found')
tmp = ROOT / '.tmp_qm_v60_client.js'
tmp.write_text(client_text[script_start + len('<script>'):script_end], encoding='utf-8')
try:
    subprocess.run(['node', '--check', str(tmp)], cwd=ROOT, check=True)
finally:
    if tmp.exists():
        tmp.unlink()

# 1) Existing start flow must still set active inspection and open the checklist
#    before the optional snapshot refresh.
start_pos = client_text.find("const result = await callServer('startQmInspection'")
modal_pos = client_text.find('openQmInspectionModal_();', start_pos)
refresh_pos = client_text.find('await loadMobileSnapshot({ silent: true, force: true });', start_pos)
if start_pos < 0 or modal_pos < 0 or refresh_pos < 0 or not (start_pos < modal_pos < refresh_pos):
    fail('QM start -> checklist modal regression guard failed')

# 2) Final save optimizations.
submit_text = client_text[client_text.find('async function submitQmInspectionFinal_'):client_text.find('function openQmInspectionModal_', client_text.find('async function submitQmInspectionFinal_'))]
if 'await saveQmInspectionDraftNow_(false);' in submit_text:
    fail('redundant final draft-save guard failed')
if 'draftRowNumber: Number(active.draft.rowNumber || 0)' not in submit_text:
    fail('QM final direct-row payload guard failed')
qm_check = QM.read_text(encoding='utf-8')
if 'function getQmChecklistForSubmit_()' not in qm_check or 'const checklist = getQmChecklistForSubmit_();' not in qm_check:
    fail('QM fast submit checklist guard failed')
if 'getQmInspectionRecordById_(String(safe.draftId).trim(), safe.draftRowNumber)' not in qm_check:
    fail('QM final direct-row lookup guard failed')

# 3) QM-only cleaner name display.
if "role === 'QM' ? (assignedNames || '정비자 미지정') : roomStatus" not in client_text:
    fail('QM cleaner-name card guard failed')

# 4) Readability and simplified guide.
if '양호/불량을 선택하세요. 불량은 내용을 입력하고' not in client_text:
    fail('QM simplified guide guard failed')
styles_check = STYLES.read_text(encoding='utf-8')
if 'NOVA v60 — QM 모바일 점검 가독성·미니멀 UI' not in styles_check or 'font-size:17px' not in styles_check:
    fail('QM readability CSS guard failed')

subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)

print('QM_MOBILE_V60_OK')
print('Changed: Client.html, 16_QmChecklist.js, Styles.html')
print('1) QM start -> checklist modal behavior preserved and guarded')
print('2) Final submit: redundant draft RPC removed; draft row direct lookup; checklist read outside write lock; response refresh nonblocking')
print('3) QM room card: room-status label replaced by assigned roommaid name(s) only for QM')
print('4) QM checklist: larger type/touch controls, shorter guide, flatter scoped UI')
print('Syntax/scope prechecks: PASS')
