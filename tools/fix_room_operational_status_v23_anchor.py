#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'tools' / 'apply_room_operational_status_realtime_v23.py'

if not PATCH.exists():
    print('PATCH_ERROR: v23 patch script not found')
    sys.exit(1)

text = PATCH.read_text(encoding='utf-8')
old = '''route_anchor = "      if (action === 'CHANGE_ROOM_STATUS') {"\nif cloud.count(route_anchor) != 1:\n    fail(f'Cloud Run CHANGE_ROOM_STATUS route anchor: expected 1 match, found {cloud.count(route_anchor)}')\n\nroute_branch = r'''\n'''
new = '''route_start_marker = "app.post(\\n  '/v1/rooms/:roomNo/action',"\nroute_end_marker = "\\napp.post(\\n  '/v1/houseman-orders',"\nroute_start = cloud.find(route_start_marker)\nif route_start < 0:\n    fail('Cloud Run room action route start not found')\nroute_end = cloud.find(route_end_marker, route_start)\nif route_end < 0:\n    fail('Cloud Run room action route end not found')\nroute_segment = cloud[route_start:route_end]\nroute_anchor = "      if (action === 'CHANGE_ROOM_STATUS') {"\nif route_segment.count(route_anchor) != 1:\n    fail(f'Cloud Run CHANGE_ROOM_STATUS route anchor inside room-action route: expected 1 match, found {route_segment.count(route_anchor)}')\n\nroute_branch = r'''\n'''
if old not in text:
    print('PATCH_ERROR: original v23 route-anchor block not found')
    sys.exit(1)
text = text.replace(old, new, 1)

old2 = "cloud = cloud.replace(route_anchor, route_branch + route_anchor, 1)"
new2 = "route_segment = route_segment.replace(route_anchor, route_branch + route_anchor, 1)\ncloud = cloud[:route_start] + route_segment + cloud[route_end:]"
if old2 not in text:
    print('PATCH_ERROR: original v23 route replacement line not found')
    sys.exit(1)
text = text.replace(old2, new2, 1)

PATCH.write_text(text, encoding='utf-8')
print('FIX_OK')
print('Fixed: Cloud Run CHANGE_ROOM_STATUS anchor is scoped to /v1/rooms/:roomNo/action only')
print('Production files unchanged')
