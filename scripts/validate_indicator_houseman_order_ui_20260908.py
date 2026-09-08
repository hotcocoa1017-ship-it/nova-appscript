from pathlib import Path
import re
import subprocess
import sys

client_path = Path('Client.html')
if not client_path.exists():
    print('MISSING: Client.html', file=sys.stderr)
    raise SystemExit(90)

text = client_path.read_text(encoding='utf-8')
errors = []
checks = []


def require(needle, label):
    ok = needle in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'MISSING: {label} :: {needle}')


def forbid(needle, label):
    ok = needle not in text
    checks.append((label, ok))
    if not ok:
        errors.append(f'FORBIDDEN: {label} :: {needle}')


require('INDICATOR_HOUSEMAN_ORDER_UI_V1', 'UI marker')
require('function indicatorRoomPendingOrderTooltip_(room)', 'room order tooltip helper')
require(".filter(order => String(order?.roomNo || '').trim() === roomNo && indicatorIsPendingHousemanOrder_(order))", 'tooltip uses only room pending orders')
require("return item || note || '오더내용 없음';", 'tooltip direct order content')
forbid('title=\"미완료 하우스맨 오더\"', 'old generic room badge tooltip removed')
require('title=\"${escapeAttr(indicatorRoomPendingOrderTooltip_(room))}\"', 'room badge direct tooltip binding')

for code in ['ROOM', 'PENDING', 'ALL']:
    require(f'data-order-list-filter=\"{code}\"', f'order filter button {code}')
require("state.indicator.orderListFilter = String(button.dataset.orderListFilter || 'ALL').toUpperCase();", 'filter click state update')
require('renderIndicatorSummary();\n        renderOrderList();', 'filter click rerender')
require("if (filter === 'PENDING') return indicatorIsPendingHousemanOrder_(order);", 'pending filter semantics')
require("if (filter === 'ROOM')", 'room filter semantics')
require("return Boolean(roomNo && roomNo !== '공용');", 'room filter excludes common orders')
require('.filter(order => indicatorOrderMatchesListFilter_(order, orderListFilter))', 'order list applies filter')
require("if (filter === 'PENDING') return '미완료 하우스맨 오더가 없습니다.';", 'pending empty-state message')
require("if (filter === 'ROOM') return '객실 하우스맨 오더가 없습니다.';", 'room empty-state message')
require("const value = String(state.indicator.orderListFilter || 'ALL')", 'default all-order compatibility')

blocks = re.findall(r'<script[^>]*>(.*?)</script>', text, flags=re.S | re.I)
if not blocks:
    errors.append('SYNTAX: no Client script block')
else:
    result = subprocess.run(['node', '--check', '-'], input='\n'.join(blocks), text=True, capture_output=True, check=False)
    checks.append(('Client JavaScript syntax', result.returncode == 0))
    if result.returncode != 0:
        errors.append(f'SYNTAX: {(result.stderr or result.stdout).strip()}')

if errors:
    print(f'Indicator houseman order UI validation FAILED: {len(errors)} issue(s).', file=sys.stderr)
    for error in errors:
        print(f' - {error}', file=sys.stderr)
    raise SystemExit(91)

print(f'Indicator houseman order UI validation PASS: {len(checks)} checks.')
