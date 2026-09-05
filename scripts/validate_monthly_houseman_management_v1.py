from pathlib import Path

checks = {
    '07_Houseman.js': [
        "String(item.data['처리상태'] || '').trim().toUpperCase() !== 'CANCELLED'",
        'MONTHLY_HOUSEMAN_MANAGEMENT_V1'
    ],
    '11_Monthly.js': [
        'function cancelMonthlyManagedHousemanOrder',
        "'처리상태': 'CANCELLED'",
        "['REGISTERED', 'ASSIGNED', 'CANCELLED'].includes(statusCode)",
        "options.housemen = getPublicStaffList_(['HOUSEMAN'])",
        'canEdit,',
        'canAssign,',
        'canCancel,',
        'canDelete,',
        "if (statusCode === 'CANCELLED') return '오더취소'"
    ],
    'Client.html': [
        'data-monthly-order-manage',
        'function openMonthlyHousemanManageModal_',
        'function saveMonthlyHousemanManagedContent_',
        'function assignMonthlyHousemanManagedOrder_',
        'function cancelMonthlyHousemanManagedOrder_',
        'function deleteMonthlyHousemanManagedOrder_',
        "callServer('updateHousemanOrder'",
        'novaRealtimeAssignHousemanOrder_',
        'novaMonthlyRealtimeCancelHousemanOrder_'
    ]
}

for path, needles in checks.items():
    text = Path(path).read_text(encoding='utf-8')
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f'{path}: missing {missing}')

monthly = Path('11_Monthly.js').read_text(encoding='utf-8')
if "requestSource || '').trim().toUpperCase() !== 'MONTHLY_HISTORY'" in monthly:
    raise SystemExit('legacy MONTHLY_HISTORY-only delete restriction still present')

print('MONTHLY_HOUSEMAN_MANAGEMENT_V1 validation PASS')
