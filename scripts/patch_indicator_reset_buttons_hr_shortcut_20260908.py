from pathlib import Path
import sys

CLIENT = Path('Client.html')
MARKER = 'INDICATOR_RESET_BUTTON_AUTHORITY_V2'
HR_MARKER = 'NOVA_HR_SHORTCUT_ROLES_V1'

text = CLIENT.read_text(encoding='utf-8')
original = text

# 1) Realtime room authority must carry the actual cleaning completion timestamps.
old_fields = "'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'"
new_fields = "'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'cleaningStartedAt', 'cleaningCompletedAt', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'"
if new_fields not in text:
    if old_fields not in text:
        raise SystemExit('ERROR: realtime room field authority anchor not found')
    text = text.replace(old_fields, new_fields, 1)

# 2) Full /v1/rooms hydrate mapper: retain DB cleaning timestamps.
old_full = "      qmEmployeeNo: String(row.qm_employee_no ?? row.qmEmployeeNo ?? ''),\n      operationalStatus: String(row.operational_status ?? row.operationalStatus ?? ''),"
new_full = "      qmEmployeeNo: String(row.qm_employee_no ?? row.qmEmployeeNo ?? ''),\n      cleaningStartedAt: row.cleaning_started_at || row.cleaningStartedAt || '',\n      cleaningCompletedAt: row.cleaning_completed_at || row.cleaningCompletedAt || '',\n      operationalStatus: String(row.operational_status ?? row.operationalStatus ?? ''),"
if new_full not in text:
    if old_full not in text:
        raise SystemExit('ERROR: full realtime room mapper anchor not found')
    text = text.replace(old_full, new_full, 1)

# 3) Partial Broadcast/reconcile mapper: retain timestamps when supplied.
old_partial = "    putText('qmEmployeeNo', 'qm_employee_no', 'qmEmployeeNo');\n    putText('operationalStatus', 'operational_status', 'operationalStatus');"
new_partial = "    putText('qmEmployeeNo', 'qm_employee_no', 'qmEmployeeNo');\n    putText('cleaningStartedAt', 'cleaning_started_at', 'cleaningStartedAt');\n    putText('cleaningCompletedAt', 'cleaning_completed_at', 'cleaningCompletedAt');\n    putText('operationalStatus', 'operational_status', 'operationalStatus');"
if new_partial not in text:
    if old_partial not in text:
        raise SystemExit('ERROR: partial realtime room mapper anchor not found')
    text = text.replace(old_partial, new_partial, 1)

# 4) Button visibility must use real DB completion evidence, not cleaningType default NORMAL.
old_reset = "    const cleaningResetAvailable = cleaningCompletionLocked\n      && Boolean(room.cleaningType || room.roommaidEmployeeNo || room.secondaryRoommaidEmployeeNo || room.qmEmployeeNo);\n    const qmClearAvailable = Boolean(String(room.qmEmployeeNo || '').trim()); // QM_CLEAR_REWORK_CONTROLS_V1"
new_reset = "    const cleaningResetAvailable = cleaningCompletionLocked\n      && Boolean(\n        String(room.cleaningCompletedAt || '').trim()\n        || String(room.roommaidEmployeeNo || '').trim()\n        || String(room.secondaryRoommaidEmployeeNo || '').trim()\n      ); // INDICATOR_RESET_BUTTON_AUTHORITY_V2\n    const qmClearAvailable = Boolean(String(room.qmEmployeeNo || '').trim()); // QM_CLEAR_REWORK_CONTROLS_V1"
if new_reset not in text:
    count = text.count(old_reset)
    if count != 1:
        raise SystemExit(f'ERROR: room reset visibility anchor count={count}, expected=1')
    text = text.replace(old_reset, new_reset, 1)

# 5) HR shortcut: ADMIN/ORDER plus requested operational roles.
old_role_gate = "    if (!['ADMIN', 'ORDER', 'HOUSEMAN'].includes(role)) return items; // HOUSEMAN_LOST_FOUND_SHORTCUT_V1"
new_role_gate = "    const hrShortcutRoles = new Set(['ADMIN', 'ORDER', 'HOUSEMAN', 'ROOMMAID', 'QM', 'PUBLIC']); // NOVA_HR_SHORTCUT_ROLES_V1\n    const lostFoundShortcutRoles = new Set(['ADMIN', 'ORDER', 'HOUSEMAN']);\n    if (!hrShortcutRoles.has(role)) return items;"
if new_role_gate not in text:
    if old_role_gate not in text:
        raise SystemExit('ERROR: menu role gate anchor not found')
    text = text.replace(old_role_gate, new_role_gate, 1)

old_lost = "    if (!items.some(item => item && item.id === 'lostFoundShortcut')) {"
new_lost = "    if (lostFoundShortcutRoles.has(role) && !items.some(item => item && item.id === 'lostFoundShortcut')) {"
if new_lost not in text:
    if old_lost not in text:
        raise SystemExit('ERROR: lost-found shortcut anchor not found')
    text = text.replace(old_lost, new_lost, 1)

old_houseman_return = "    if (role === 'HOUSEMAN') return items; // HOUSEMAN은 습득물 관리 바로가지만 추가\n"
if old_houseman_return in text:
    text = text.replace(old_houseman_return, '', 1)

# Validate exact intended behavior markers.
required = [
    MARKER,
    HR_MARKER,
    "'cleaningStartedAt', 'cleaningCompletedAt'",
    "cleaningCompletedAt: row.cleaning_completed_at || row.cleaningCompletedAt || ''",
    "putText('cleaningCompletedAt', 'cleaning_completed_at', 'cleaningCompletedAt');",
    "String(room.cleaningCompletedAt || '').trim()",
    "new Set(['ADMIN', 'ORDER', 'HOUSEMAN', 'ROOMMAID', 'QM', 'PUBLIC'])",
    "lostFoundShortcutRoles.has(role)",
    "label: 'NOVA 통합 인사시스템 ↗'",
]
for needle in required:
    if needle not in text:
        raise SystemExit(f'ERROR: validation missing {needle}')

if "if (role === 'HOUSEMAN') return items" in text:
    raise SystemExit('ERROR: HOUSEMAN still exits before HR shortcut')
if "Boolean(room.cleaningType || room.roommaidEmployeeNo || room.secondaryRoommaidEmployeeNo || room.qmEmployeeNo)" in text:
    raise SystemExit('ERROR: old cleaning reset proxy condition still present')

if text == original:
    print('Patch already applied; no source change needed.')
else:
    CLIENT.write_text(text, encoding='utf-8')
    print('Indicator reset-button authority and HR shortcuts patched.')
