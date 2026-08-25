#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / 'tools' / 'apply_realtime_roommaid_assignment_v20.py'

if not PATCHER.exists():
    print('PATCH_ERROR: original patcher not found')
    sys.exit(1)

text = PATCHER.read_text(encoding='utf-8')
old = """route_start = cloud.find(\"app.post('/v1/rooms/:roomNo/action', async (req, res, next) => {\")\nroute_end = cloud.find(\"\\n\\n/**\\n * 하우스맨 오더 Realtime 선등록.\", route_start)\nif route_start < 0 or route_end < 0:\n    fail('Cloud Run room action route markers not found')\n"""
new = """route_start = cloud.find(\"app.post('/v1/rooms/:roomNo/action', async (req, res, next) => {\")\n# Cloud Run 파일의 주석 문구는 버전별로 달라질 수 있으므로 다음 실제 라우트를 경계로 사용한다.\nhouseman_route = cloud.find(\"app.post('/v1/houseman-orders'\", route_start)\nif route_start < 0 or houseman_route < 0:\n    fail('Cloud Run room/houseman route markers not found')\n# 하우스맨 라우트 직전 설명 주석이 있으면 그대로 보존한다.\ncomment_start = cloud.rfind('\\n/**', route_start, houseman_route)\nroute_end = comment_start + 1 if comment_start >= 0 else houseman_route\n"""

if old not in text:
    # 이미 수정된 경우 그대로 실행한다.
    if "houseman_route = cloud.find(\"app.post('/v1/houseman-orders'\"" not in text:
        print('PATCH_ERROR: expected marker block not found in patcher')
        sys.exit(1)
else:
    PATCHER.write_text(text.replace(old, new, 1), encoding='utf-8')

subprocess.run([sys.executable, str(PATCHER)], cwd=ROOT, check=True)
