from pathlib import Path

client = Path('Client.html').read_text(encoding='utf-8')
migration = Path('supabase/migrations/20260909_room_last_qm_card_v1.sql').read_text(encoding='utf-8')

required_client = [
    'ROOM_LAST_QM_CARD_V1',
    "'lastQmBusinessDate', 'lastQmEmployeeNo'",
    "lastQmBusinessDate: String(row.last_qm_business_date",
    "lastQmEmployeeNo: String(row.last_qm_employee_no",
    "putText('lastQmBusinessDate', 'last_qm_business_date', 'lastQmBusinessDate');",
    "putText('lastQmEmployeeNo', 'last_qm_employee_no', 'lastQmEmployeeNo');",
    'function indicatorLastQmDisplayDate_',
    "['VACANT_CLEAN', 'STOCK', 'STOCK_RC', 'STOCK_HU']",
    '최종점검 ${escapeHtml(lastQmDisplayDate)}',
]
required_migration = [
    'room_last_qm_state_v1',
    'last_qm_business_date',
    'last_qm_employee_no',
    'trg_nova_room_last_qm_state_v1',
    'trg_nova_rooms_current_last_qm_carry_v1',
    "v_action = 'QM_COMPLETE'",
    "v_action = 'CLEANING_COMPLETE'",
    "v_after_status = 'DUE_OUT'",
    "v_after_status like 'CHECKED_OUT%'",
    "source_type = 'WORK_HISTORY'",
    'record_type = \'QM_COMPLETE\'',
]

for needle in required_client:
    if needle not in client:
        raise SystemExit(f'FAIL client missing: {needle}')
for needle in required_migration:
    if needle not in migration:
        raise SystemExit(f'FAIL migration missing: {needle}')

# The requested card text must not add the room-status word "미판매".
if '미판매 최종점검' in client:
    raise SystemExit('FAIL card text contains unwanted 미판매 prefix')

# Do not alter existing operational columns through the migration.
for forbidden in [
    'drop column room_status',
    'drop column cleaning_status',
    'drop table public.nova_rooms_current',
    'truncate public.nova_rooms_current',
    'delete from public.nova_rooms_current',
    'delete from public.nova_qm_inspections',
]:
    if forbidden in migration.lower():
        raise SystemExit(f'FAIL destructive migration token: {forbidden}')

print('PASS ROOM_LAST_QM_CARD_V1 source invariants')
