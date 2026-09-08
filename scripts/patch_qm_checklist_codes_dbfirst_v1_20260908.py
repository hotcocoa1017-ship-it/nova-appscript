from pathlib import Path
import sys

MARKER = 'NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1'


def fail(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    raise SystemExit(98)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and new in text:
        return text
    fail(f'{label}: expected 1 anchor, found {count}')


# 1) DB RPC allowlist.
p = Path('DbFirstBridge.js')
s = p.read_text(encoding='utf-8')
old = "    'nova_admin_code_settings_disable_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1\n    'nova_monthly_history_v1',"
new = "    'nova_admin_code_settings_disable_v1', // NOVA_ADMIN_CODE_SETTINGS_DB_FIRST_V1\n    'nova_qm_checklist_codes_read_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1\n    'nova_qm_checklist_place_save_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1\n    'nova_qm_checklist_item_save_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1\n    'nova_qm_checklist_item_disable_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1\n    'nova_qm_checklist_place_disable_v1', // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1\n    'nova_monthly_history_v1',"
s = replace_once(s, old, new, 'QM checklist RPC allowlist')
p.write_text(s, encoding='utf-8')

# 2) Management UI routes only; UI markup stays unchanged.
p = Path('Client.html')
s = p.read_text(encoding='utf-8')
s = replace_once(s,
    "callServer('getQmChecklistManagementData', state.token)",
    "callServer('getQmChecklistManagementDataDbFirst', state.token) // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM management read route')
s = replace_once(s,
    "callServer('saveQmChecklistPlace', state.token, payload)",
    "callServer('saveQmChecklistPlaceDbFirst', state.token, Object.assign({}, payload, { requestId: novaRealtimeRequestId_('QM_PLACE_SAVE_V1', 'CONFIG') })) // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM place save route')
s = replace_once(s,
    "callServer('deleteQmChecklistPlace', state.token, { code })",
    "callServer('deleteQmChecklistPlaceDbFirst', state.token, { code, requestId: novaRealtimeRequestId_('QM_PLACE_DISABLE_V1', 'CONFIG') }) // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM place disable route')
s = replace_once(s,
    "callServer('saveQmChecklistItem', state.token, payload)",
    "callServer('saveQmChecklistItemDbFirst', state.token, Object.assign({}, payload, { requestId: novaRealtimeRequestId_('QM_ITEM_SAVE_V1', 'CONFIG') })) // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM item save route')
s = replace_once(s,
    "callServer('deleteQmChecklistItem', state.token, { code })",
    "callServer('deleteQmChecklistItemDbFirst', state.token, { code, requestId: novaRealtimeRequestId_('QM_ITEM_DISABLE_V1', 'CONFIG') }) // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM item disable route')
p.write_text(s, encoding='utf-8')

# 3) QM execution paths read the same DB definition/revision.
p = Path('16_QmChecklist.js')
s = p.read_text(encoding='utf-8')
s = replace_once(s,
    "const checklist = realtimeStarted ? getQmChecklistForSubmit_() : getQmChecklistForMobile_();",
    "const checklist = realtimeStarted ? getQmChecklistForSubmitDbFirst_(token) : getQmChecklistForMobileDbFirst_(token); // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM start checklist DB read')
legacy_submit = "const checklist = getQmChecklistForSubmit_();"
new_submit = "const checklist = getQmChecklistForSubmitDbFirst_(token); // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1"
count = s.count(legacy_submit)
if count:
    if count != 3:
        fail(f'QM submit checklist DB reads: expected 3 anchors, found {count}')
    s = s.replace(legacy_submit, new_submit)
elif s.count(new_submit) < 3:
    fail('QM submit checklist DB reads missing')
s = replace_once(s,
    "const targetPhotos = getQmDraftTargetPhotos_(detail, targetType, targetCode, true);",
    "const targetPhotos = getQmDraftTargetPhotos_(detail, targetType, targetCode, true, getQmChecklistForSubmitDbFirst_(token).items); // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM photo checklist DB read')
s = replace_once(s,
    "function getQmDraftTargetPhotos_(detail, targetType, targetCode, createMissing) {",
    "function getQmDraftTargetPhotos_(detail, targetType, targetCode, createMissing, checklistItems) { // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM photo helper signature')
s = replace_once(s,
    "const checklistItem = getActiveQmChecklistItems_().find(item => item.code === targetCode);",
    "const checklistItem = (Array.isArray(checklistItems) ? checklistItems : getActiveQmChecklistItems_()).find(item => item.code === targetCode); // NOVA_QM_CHECKLIST_CODES_DB_FIRST_V1",
    'QM photo missing answer DB definition')
p.write_text(s, encoding='utf-8')

# 4) Canonical meta-patcher owns this cutover on every deployment.
p = Path('scripts/fix_patch_site_scope_v2.py')
s = p.read_text(encoding='utf-8')
anchor = "subprocess.run([sys.executable, 'scripts/patch_admin_code_settings_dbfirst_v1_20260908.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/validate_admin_code_settings_dbfirst_v1_20260908.py'], check=True)\n"
insert = anchor + "\n# QM 체크리스트/점검장소 정의도 동일 code master의 DB authority를 사용합니다.\n# ADMIN/ORDER 관리권한과 QM 읽기권한을 보존하며 Sheet는 DB 확정 후 호환 미러입니다.\nsubprocess.run([sys.executable, 'scripts/patch_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)\nsubprocess.run([sys.executable, 'scripts/validate_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)\n"
if 'patch_qm_checklist_codes_dbfirst_v1_20260908.py' not in s:
    if anchor not in s:
        fail('canonical admin-code anchor missing')
    s = s.replace(anchor, insert, 1)
p.write_text(s, encoding='utf-8')

print('QM checklist/place code master DB-first patch applied.')
