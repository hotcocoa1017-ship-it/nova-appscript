from pathlib import Path

MARKER = 'HOUSEMAN_LATEST_REGISTERED_LISTS_V1'

monthly_path = Path('11_Monthly.js')
client_path = Path('Client.html')

monthly = monthly_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')

old_monthly = """function compareMonthlyItems_(a, b) { // (월별 최신순 정렬)\n  return String(b.businessDate).localeCompare(String(a.businessDate))\n    || String(b.eventAt).localeCompare(String(a.eventAt))\n    || String(a.roomNo).localeCompare(String(b.roomNo), 'ko', { numeric: true });\n}"""
new_monthly = """function compareMonthlyItems_(a, b) { // (월별 최신순 정렬 · 하우스맨은 등록일시 최신 우선) // HOUSEMAN_LATEST_REGISTERED_LISTS_V1\n  const businessDateCompare = String(b.businessDate || '').localeCompare(String(a.businessDate || ''));\n  if (businessDateCompare) return businessDateCompare;\n  if (a.typeCode === 'HOUSEMAN' && b.typeCode === 'HOUSEMAN') {\n    return String(b.registeredAt || '').localeCompare(String(a.registeredAt || ''))\n      || Number(b.rowNumber || 0) - Number(a.rowNumber || 0)\n      || String(a.roomNo || '').localeCompare(String(b.roomNo || ''), 'ko', { numeric: true });\n  }\n  return String(b.eventAt || '').localeCompare(String(a.eventAt || ''))\n    || String(a.roomNo || '').localeCompare(String(b.roomNo || ''), 'ko', { numeric: true });\n}"""
if MARKER not in monthly:
    if monthly.count(old_monthly) != 1:
        raise SystemExit(f'11_Monthly comparator anchor expected once, found {monthly.count(old_monthly)}')
    monthly = monthly.replace(old_monthly, new_monthly, 1)

old_client = """  function renderOrderList() { // (처리현황 내부 스크롤 목록)\n    const container = $('orderScroll');\n    if (!container) return;\n    const scrollTop = container.scrollTop;\n    const orders = state.indicator.data?.orders || [];"""
new_client = """  function renderOrderList() { // (처리현황 내부 스크롤 목록)\n    const container = $('orderScroll');\n    if (!container) return;\n    const scrollTop = container.scrollTop;\n    const orders = [...(state.indicator.data?.orders || [])].sort((a, b) =>\n      String(b.registeredAt || '').localeCompare(String(a.registeredAt || ''))\n      || Number(b.rowNumber || 0) - Number(a.rowNumber || 0)\n    ); // HOUSEMAN_LATEST_REGISTERED_LISTS_V1 · 통합인디케이터 최근 등록순 고정"""
if MARKER not in client:
    if client.count(old_client) != 1:
        raise SystemExit(f'Client renderOrderList anchor expected once, found {client.count(old_client)}')
    client = client.replace(old_client, new_client, 1)

# Existing server ordering must remain registeredAt-first.
houseman = Path('07_Houseman.js').read_text(encoding='utf-8')
required = [
    'HOUSEMAN_LATEST_FIRST_V1',
    "String(b.registeredAt || '')",
    "HOUSEMAN_LATEST_REGISTERED_LISTS_V1",
]
for item in required[:2]:
    if item not in houseman:
        raise SystemExit('07_Houseman latest-registration server ordering missing: ' + item)
for label, text in [('11_Monthly.js', monthly), ('Client.html', client)]:
    if MARKER not in text:
        raise SystemExit(label + ' marker missing')

monthly_path.write_text(monthly, encoding='utf-8')
client_path.write_text(client, encoding='utf-8')
print('HOUSEMAN latest-registration list patch applied')
