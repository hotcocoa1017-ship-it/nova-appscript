from pathlib import Path

client = Path('Client.html').read_text(encoding='utf-8')
photo = Path('HousemanRequestPhoto.js').read_text(encoding='utf-8')

checks = {
    'client marker': 'QM_HOUSEMAN_REQUEST_PARITY_V1' in client,
    'qm fast create enabled': "!['ROOMMAID', 'QM'].includes(role)" in client,
    'qm request source': 'requestSource: role' in client,
    'qm legacy fallback': '하우스맨 DB 우선등록 실패 · 기존 모바일 요청으로 fallback' in client,
    'backend mobile request preserved': "runMobileAction_('createMobileHousemanRequest'" in client,
    'photo marker': 'QM_HOUSEMAN_REQUEST_PARITY_V1' in photo,
    'photo qm capability': "enabled: ['ROOMMAID', 'QM'].includes(role)" in photo,
    'photo qm upload role': "if (!['ROOMMAID', 'QM'].includes(role))" in photo,
    'photo source ownership': 'requestSource !== role' in photo,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('QM houseman request parity validation failed: ' + ', '.join(failed))
print('QM_HOUSEMAN_REQUEST_PARITY_V1 validation PASS')
