#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'tools' / 'apply_room_operational_status_realtime_v23.py'

if not PATCH.exists():
    print('PATCH_ERROR: v23 patch script not found')
    sys.exit(1)

text = PATCH.read_text(encoding='utf-8')

old = (
    "route_anchor = \"      if (action === 'CHANGE_ROOM_STATUS') {\"\n"
    "if cloud.count(route_anchor) != 1:\n"
    "    fail(f'Cloud Run CHANGE_ROOM_STATUS route anchor: expected 1 match, found {cloud.count(route_anchor)}')\n"
    "\n"
    "route_branch = r" + "'''"
)

new = (
    "route_start_marker = \"app.post(\\n  '/v1/rooms/:roomNo/action',\"\n"
    "route_end_marker = \"\\napp.post(\\n  '/v1/houseman-orders',\"\n"
    "route_start = cloud.find(route_start_marker)\n"
    "if route_start < 0:\n"
    "    fail('Cloud Run room action route start not found')\n"
    "route_end = cloud.find(route_end_marker, route_start)\n"
    "if route_end < 0:\n"
    "    fail('Cloud Run room action route end not found')\n"
    "route_segment = cloud[route_start:route_end]\n"
    "route_anchor = \"      if (action === 'CHANGE_ROOM_STATUS') {\"\n"
    "if route_segment.count(route_anchor) != 1:\n"
    "    fail(f'Cloud Run CHANGE_ROOM_STATUS route anchor inside room-action route: expected 1 match, found {route_segment.count(route_anchor)}')\n"
    "\n"
    "route_branch = r" + "'''"
)

if text.count(old) != 1:
    print(f'PATCH_ERROR: original v23 route-anchor block expected 1 match, found {text.count(old)}')
    sys.exit(1)
text = text.replace(old, new, 1)

old2 = "cloud = cloud.replace(route_anchor, route_branch + route_anchor, 1)"
new2 = (
    "route_segment = route_segment.replace(route_anchor, route_branch + route_anchor, 1)\n"
    "cloud = cloud[:route_start] + route_segment + cloud[route_end:]"
)
if text.count(old2) != 1:
    print(f'PATCH_ERROR: original v23 route replacement expected 1 match, found {text.count(old2)}')
    sys.exit(1)
text = text.replace(old2, new2, 1)

PATCH.write_text(text, encoding='utf-8')
print('FIX_OK')
print('Fixed: Cloud Run CHANGE_ROOM_STATUS anchor is scoped to /v1/rooms/:roomNo/action only')
print('Production files unchanged')
