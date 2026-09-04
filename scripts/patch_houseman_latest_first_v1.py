from pathlib import Path
import sys

MARKER = 'HOUSEMAN_LATEST_FIRST_V1'

houseman_path = Path('07_Houseman.js')
mobile_path = Path('10_Mobile.js')
client_path = Path('Client.html')

houseman = houseman_path.read_text(encoding='utf-8')
mobile = mobile_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')

# 1) 서버 공통 하우스맨 오더 조회: 수정일시가 아니라 등록일시 최신순.
old_houseman_sort = """      .sort(\n        (a, b) =>\n          String(b.updatedAt)\n            .localeCompare(\n              String(a.updatedAt)\n            )\n          ||\n          String(b.registeredAt)\n            .localeCompare(\n              String(a.registeredAt)\n            )\n      );"""
new_houseman_sort = """      .sort(\n        (a, b) =>\n          String(b.registeredAt || '')\n            .localeCompare(\n              String(a.registeredAt || '')\n            )\n          ||\n          Number(b.rowNumber || 0)\n            - Number(a.rowNumber || 0)\n      ); // HOUSEMAN_LATEST_FIRST_V1 · 신규 등록시간 최신순"""
if MARKER not in houseman:
    if old_houseman_sort not in houseman:
        raise SystemExit('07_Houseman.js latest-first sort anchor not found')
    houseman = houseman.replace(old_houseman_sort, new_houseman_sort, 1)

# 2) 하우스맨 직원 모바일: 미처리 오더는 기존처럼 완료보다 위에 두되,
#    미처리 그룹 내부에서는 중요/인수인계보다 등록시간 최신순을 우선합니다.
old_mobile_compare = """function compareMobileOrders_(a, b) { // (모바일 오더 우선순위 정렬)\n  const completed = new Set(['COMPLETED', 'UNABLE']);\n  const aDone = completed.has(a.statusCode) ? 1 : 0;\n  const bDone = completed.has(b.statusCode) ? 1 : 0;\n  if (aDone !== bDone) return aDone - bDone;\n  if (a.important !== b.important) return a.important ? -1 : 1;\n  if (a.handover !== b.handover) return a.handover ? -1 : 1;\n  return String(b.updatedAt).localeCompare(String(a.updatedAt));\n}"""
new_mobile_compare = """function compareMobileOrders_(a, b) { // (모바일 오더 최신 등록 우선 정렬 · HOUSEMAN_LATEST_FIRST_V1)\n  const completed = new Set(['COMPLETED', 'UNABLE']);\n  const aDone = completed.has(a.statusCode) ? 1 : 0;\n  const bDone = completed.has(b.statusCode) ? 1 : 0;\n  if (aDone !== bDone) return aDone - bDone;\n  const registeredCompare = String(b.registeredAt || '').localeCompare(String(a.registeredAt || ''));\n  if (registeredCompare) return registeredCompare;\n  if (a.important !== b.important) return a.important ? -1 : 1;\n  if (a.handover !== b.handover) return a.handover ? -1 : 1;\n  return Number(b.rowNumber || 0) - Number(a.rowNumber || 0);\n}"""
if MARKER not in mobile:
    if old_mobile_compare not in mobile:
        raise SystemExit('10_Mobile.js mobile order comparator anchor not found')
    mobile = mobile.replace(old_mobile_compare, new_mobile_compare, 1)

# 3) 관리자/오더테이커 Realtime DB 보정 후에도 동일하게 등록일시 최신순 유지.
old_client_sort = "orders.sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')) || String(b.registeredAt || '').localeCompare(String(a.registeredAt || '')));"
new_client_sort = "orders.sort((a, b) => String(b.registeredAt || '').localeCompare(String(a.registeredAt || '')) || Number(b.rowNumber || 0) - Number(a.rowNumber || 0)); // HOUSEMAN_LATEST_FIRST_V1"
if MARKER not in client:
    if old_client_sort not in client:
        raise SystemExit('Client.html indicator houseman sort anchor not found')
    client = client.replace(old_client_sort, new_client_sort, 1)

# Safety: new registrations must sort ahead of older active orders, while completed/unable remain after active orders.
required_houseman = [
    'HOUSEMAN_LATEST_FIRST_V1',
    "String(b.registeredAt || '')",
    'Number(b.rowNumber || 0)',
]
required_mobile = [
    'HOUSEMAN_LATEST_FIRST_V1',
    "const completed = new Set(['COMPLETED', 'UNABLE']);",
    'if (aDone !== bDone) return aDone - bDone;',
    "String(b.registeredAt || '').localeCompare(String(a.registeredAt || ''))",
]
required_client = [
    'HOUSEMAN_LATEST_FIRST_V1',
    "orders.sort((a, b) => String(b.registeredAt || '')",
    'renderOrderList();',
]
for label, text, required in [
    ('07_Houseman.js', houseman, required_houseman),
    ('10_Mobile.js', mobile, required_mobile),
    ('Client.html', client, required_client),
]:
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(f'{label} safety validation failed: ' + ', '.join(missing))

# Old problematic priority must be gone from the exact common list sort.
if old_houseman_sort in houseman:
    raise SystemExit('Old updatedAt-first server sort still present')
if old_mobile_compare in mobile:
    raise SystemExit('Old important/handover-before-time mobile comparator still present')
if old_client_sort in client:
    raise SystemExit('Old updatedAt-first client sort still present')

houseman_path.write_text(houseman, encoding='utf-8')
mobile_path.write_text(mobile, encoding='utf-8')
client_path.write_text(client, encoding='utf-8')
print('Applied HOUSEMAN_LATEST_FIRST_V1: registration time latest-first with active orders preserved above completed.')
