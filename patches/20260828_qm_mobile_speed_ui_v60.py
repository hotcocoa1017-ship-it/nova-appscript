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


# -----------------------------------------------------------------------------
# 1) Client: final QM submit already carries current answers/defects, so do not
#    make a separate draft-save RPC immediately before final submit.
#    Also do not block the completion interaction on the post-save snapshot.
# -----------------------------------------------------------------------------
client = CLIENT.read_text(encoding='utf-8')
start = client.find("  async function submitQmInspectionFinal_(event)")
end = client.find("\n  function ", start + 10)
if start < 0 or end < 0:
    fail('QM final submit function not found')
segment = client[start:end]
old = """    try {\n      await saveQmInspectionDraftNow_(false);\n      const result = await callServer('submitQmChecklistInspection', state.token, {\n"""
new = """    try {\n      // 최종제출 payload 자체에 현재 answers/defects가 모두 포함되므로\n      // 완료 직전 별도 임시저장 RPC를 반복하지 않는다.\n      const result = await callServer('submitQmChecklistInspection', state.token, {\n"""
segment = replace_once(segment, old, new, 'remove redundant QM draft save before final submit')
old = """      showToast(result.message || '점검결과를 저장했습니다.');\n      await loadMobileSnapshot({ silent: true, force: true });\n"""
new = """      showToast(result.message || '점검결과를 저장했습니다.');\n      // 완료 성공 응답을 먼저 사용자에게 돌려주고, 카드 최신화는 뒤에서 수행한다.\n      loadMobileSnapshot({ silent: true, force: true }).catch(error => console.warn('[NOVA QM] 완료 후 화면갱신 실패:', error));\n"""
segment = replace_once(segment, old, new, 'nonblocking QM post-submit refresh')
client = client[:start] + segment + client[end:]

# QM card subtitle: show actual cleaner name instead of room-status label.
old = """      <div class=\"mobile-room-status\"><b>${escapeHtml(roomStatus)}</b><span>${escapeHtml(cleaningStatus)}</span></div>\n"""
new = """      <div class=\"mobile-room-status\"><b>${escapeHtml(role === 'QM' ? (assignedNames || '-') : roomStatus)}</b><span>${escapeHtml(cleaningStatus)}</span></div>\n"""
client = replace_once(client, old, new, 'QM room card cleaner name')
CLIENT.write_text(client, encoding='utf-8')


# -----------------------------------------------------------------------------
# 2) Server: keep checklist initialization/migration on start/admin paths, but
#    final-submit only needs a read-only active snapshot. Build it with one code
#    table read and do that before acquiring the global write lock.
# -----------------------------------------------------------------------------
qm = QM.read_text(encoding='utf-8')
submit_start = qm.find('function submitQmChecklistInspection(token, payload)')
submit_end = qm.find('\nfunction getQmInspectionAnalytics(', submit_start)
if submit_start < 0 or submit_end < 0:
    fail('submitQmChecklistInspection block not found')
submit = qm[submit_start:submit_end]
old = """    const writeLock = acquireWriteLock_();\n    try {\n\n    const checklist = getQmChecklistForMobile_();\n    if (!checklist.items.length) throw new Error('사용 중인 QM 체크리스트가 없습니다. 관리자 또는 오더테이커가 체크리스트를 등록해야 합니다.');\n    if (safe.revision && String(safe.revision) !== checklist.revision) throw new Error('체크리스트가 변경되었습니다. 화면을 새로고침한 뒤 다시 작성하세요.');\n\n"""
new = """    // 체크리스트 조회는 읽기 작업이므로 전역 쓰기잠금 밖에서 처리한다.\n    // 점검완료의 잠금 대기시간을 줄이고 다른 객실 작업을 불필요하게 막지 않는다.\n    const checklist = getQmChecklistForSubmit_();\n    if (!checklist.items.length) throw new Error('사용 중인 QM 체크리스트가 없습니다. 관리자 또는 오더테이커가 체크리스트를 등록해야 합니다.');\n    if (safe.revision && String(safe.revision) !== checklist.revision) throw new Error('체크리스트가 변경되었습니다. 화면을 새로고침한 뒤 다시 작성하세요.');\n\n    const writeLock = acquireWriteLock_();\n    try {\n\n"""
submit = replace_once(submit, old, new, 'move QM checklist read before lock')

# Avoid a full user-index read solely to compose a response object. The client
# reloads its mobile snapshot after success and only needs the result fields.
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
# 3) QM checklist mobile UI only: larger readable text, larger controls, simpler
#    white surfaces and spacing. No global component/style changes.
# -----------------------------------------------------------------------------
styles = STYLES.read_text(encoding='utf-8')
css = r"""

/* NOVA v60 — QM 모바일 점검 가독성·미니멀 UI */
.qm-checklist-modal.rc3 .modal-header h2{font-size:20px;line-height:1.3}
.qm-checklist-modal.rc3 .modal-header p{font-size:14px;line-height:1.45}
.qm-checklist-modal.rc3 .qm-checklist-guide{padding:10px 2px;margin-bottom:8px;background:#fff;border-radius:0;font-size:14px;line-height:1.55}
.qm-checklist-modal.rc3 .qm-checklist-guide>span{font-size:14px;color:#475569}
.qm-checklist-modal.rc3 .qm-checklist-place-list{gap:8px}
.qm-checklist-modal.rc3 .qm-inspection-place{background:#fff;border-radius:9px}
.qm-checklist-modal.rc3 .qm-inspection-place>summary{padding:14px 12px}
.qm-checklist-modal.rc3 .qm-inspection-place>summary strong{font-size:18px;line-height:1.3}
.qm-checklist-modal.rc3 .qm-inspection-place>summary span{font-size:13px;font-weight:700}
.qm-checklist-modal.rc3 .qm-place-items,.qm-checklist-modal.rc3 .qm-custom-defects{gap:8px;padding:8px 10px 12px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item.rc3{grid-template-columns:1fr;gap:10px;padding:14px;border-radius:8px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-heading{gap:7px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-heading strong{font-size:17px;line-height:1.45}
.qm-checklist-modal.rc3 .qm-checklist-inspection-heading span{font-size:12px;padding:4px 7px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item label,.qm-checklist-modal.rc3 .qm-custom-defect label{font-size:14px;gap:7px;font-weight:700;color:#475569}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item select,.qm-checklist-modal.rc3 .qm-checklist-inspection-item textarea,.qm-checklist-modal.rc3 .qm-checklist-inspection-item input,.qm-checklist-modal.rc3 .qm-custom-defect textarea{font-size:16px;min-height:48px;padding:11px 12px;border-radius:8px}
.qm-checklist-modal.rc3 .qm-checklist-inspection-item textarea,.qm-checklist-modal.rc3 .qm-custom-defect textarea{min-height:76px;line-height:1.5}
.qm-checklist-modal.rc3 .qm-photo-control{gap:8px}
.qm-checklist-modal.rc3 .qm-add-defect{min-height:46px;font-size:15px}
.qm-checklist-modal.rc3 .modal-actions.sticky{gap:8px;padding-top:10px}
.qm-checklist-modal.rc3 .modal-actions.sticky button{min-height:52px;font-size:16px;font-weight:800}
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
# Validation
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

if "role === 'QM' ? (assignedNames || '-') : roomStatus" not in client_text:
    fail('QM cleaner-name card guard failed')
if "await saveQmInspectionDraftNow_(false);" in client_text[client_text.find('async function submitQmInspectionFinal_'):client_text.find('function openQmInspectionModal_', client_text.find('async function submitQmInspectionFinal_'))]:
    fail('redundant final draft-save guard failed')
qm_check = QM.read_text(encoding='utf-8')
if 'function getQmChecklistForSubmit_()' not in qm_check or 'const checklist = getQmChecklistForSubmit_();' not in qm_check:
    fail('QM fast submit checklist guard failed')
styles_check = STYLES.read_text(encoding='utf-8')
if 'NOVA v60 — QM 모바일 점검 가독성·미니멀 UI' not in styles_check or 'font-size:18px' not in styles_check:
    fail('QM readability CSS guard failed')
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)

print('QM_MOBILE_V60_OK')
print('Changed: Client.html, 16_QmChecklist.js, Styles.html')
print('1) QM start -> checklist modal behavior preserved')
print('2) Final submit: redundant draft RPC removed; checklist read outside write lock; response user-index read removed')
print('3) QM room card: room-status label replaced by assigned roommaid name(s)')
print('4) QM checklist: larger type/controls and simpler scoped mobile UI')
print('Syntax/release prechecks: PASS')
