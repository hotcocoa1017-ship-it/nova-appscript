#!/usr/bin/env python3
from pathlib import Path
import sys

SCRIPT = Path(__file__).resolve().parent / 'apply_room_status_realtime_v22.py'
text = SCRIPT.read_text(encoding='utf-8')
old = '''# Insert general room status branch immediately before existing QM_ASSIGN branch.\nqm_anchor = "      if (action === 'QM_ASSIGN') {"\nif cloud.count(qm_anchor) != 1:\n    fail(f'Cloud Run QM branch anchor: expected 1 match, found {cloud.count(qm_anchor)}')\n'''
new = '''# Insert general room status branch immediately before the QM_ASSIGN branch inside\n# the /v1/rooms/:roomNo/action route only. The same text also exists in other\n# mappings, so search globally would be ambiguous.\nqm_anchor = "      if (action === 'QM_ASSIGN') {"\nroom_route_marker = "  '/v1/rooms/:roomNo/action',"\nroom_route_pos = cloud.find(room_route_marker)\nif room_route_pos < 0:\n    fail('Cloud Run room action route marker not found')\nqm_pos = cloud.find(qm_anchor, room_route_pos)\nif qm_pos < 0:\n    fail('Cloud Run QM branch anchor not found inside room action route')\nnext_route_pos = cloud.find("\\napp.", room_route_pos + len(room_route_marker))\nif next_route_pos >= 0 and qm_pos >= next_route_pos:\n    fail('Cloud Run QM branch anchor resolved outside room action route')\n'''
if old not in text:
    print('FIX_ERROR: expected old QM anchor block not found')
    sys.exit(1)
text = text.replace(old, new, 1)
old_apply = "cloud = cloud.replace(qm_anchor, status_route + qm_anchor, 1)"
new_apply = "cloud = cloud[:qm_pos] + status_route + cloud[qm_pos:]"
if old_apply not in text:
    print('FIX_ERROR: expected old QM anchor apply line not found')
    sys.exit(1)
text = text.replace(old_apply, new_apply, 1)
SCRIPT.write_text(text, encoding='utf-8')
print('FIX_OK')
print('Fixed: Cloud Run QM anchor is now scoped to /v1/rooms/:roomNo/action only')
print('Production files unchanged')
