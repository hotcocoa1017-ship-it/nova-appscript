from pathlib import Path

PATH = Path('cloudrun/index.js')
text = PATH.read_text(encoding='utf-8')

route_anchor = "app.get(\n  '/v1/houseman-orders',"
start = text.find(route_anchor)
if start < 0:
    raise SystemExit('HOUSEMAN GET route anchor not found')
end = text.find("\napp.post(\n  '/v1/houseman-orders',", start)
if end < 0:
    raise SystemExit('HOUSEMAN GET route end not found')

block = text[start:end]
old = """      if (!allowedForSite(user, site)) {
        throw httpError(403, 'FORBIDDEN', '해당 사업장 조회 권한이 없습니다.');
      }
"""
new = """      // HOUSEMAN은 아래 SQL에서 본인 배정/처리/공동전달 후보만 반환하므로
      // default_site/allowed_sites로 다시 차단하지 않는다. ADMIN/ORDER만 기존 사업장 권한을 유지한다.
      if (role !== 'HOUSEMAN' && !allowedForSite(user, site)) {
        throw httpError(403, 'FORBIDDEN', '해당 사업장 조회 권한이 없습니다.');
      }
"""

if new not in block:
    if old not in block:
        raise SystemExit('HOUSEMAN site permission target not found')
    block = block.replace(old, new, 1)
    text = text[:start] + block + text[end:]

# Guard: HOUSEMAN query must remain employee-scoped.
check_start = text.find(route_anchor)
check_end = text.find("\napp.post(\n  '/v1/houseman-orders',", check_start)
check = text[check_start:check_end]
required = [
    "role !== 'HOUSEMAN' && !allowedForSite(user, site)",
    "assigned_employee_no=$3",
    "processor_employee_no=$3",
    "route_candidate_employee_nos",
]
for token in required:
    if token not in check:
        raise SystemExit(f'HOUSEMAN permission guard failed: {token}')

PATH.write_text(text, encoding='utf-8')
print('HOUSEMAN_SITE_PERMISSION_V92_OK')
