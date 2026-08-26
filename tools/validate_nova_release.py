#!/usr/bin/env python3
# NOVA production automation bootstrap: validation/deploy pipeline verified configuration marker.
from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
notes = []


def require_file(path: str):
    p = ROOT / path
    if not p.exists():
        errors.append(f"필수 파일 누락: {path}")
        return None
    return p


def require_marker(path: str, marker: str, label: str):
    p = require_file(path)
    if not p:
        return
    text = p.read_text(encoding="utf-8")
    if marker not in text:
        errors.append(f"보호 마커 누락: {label} ({path})")


# 1) 프로젝트/배포 기본 구조
clasp = require_file('.clasp.json')
manifest = require_file('appsscript.json')
if clasp:
    try:
        cfg = json.loads(clasp.read_text(encoding='utf-8'))
        if not str(cfg.get('scriptId', '')).strip():
            errors.append('.clasp.json scriptId가 비어 있습니다.')
    except Exception as exc:
        errors.append(f'.clasp.json 파싱 실패: {exc}')
if manifest:
    try:
        app = json.loads(manifest.read_text(encoding='utf-8'))
        if app.get('runtimeVersion') != 'V8':
            errors.append('appsscript.json runtimeVersion은 V8이어야 합니다.')
        webapp = app.get('webapp') or {}
        if webapp.get('executeAs') != 'USER_DEPLOYING':
            errors.append('웹앱 executeAs 설정이 변경되었습니다.')
    except Exception as exc:
        errors.append(f'appsscript.json 파싱 실패: {exc}')

# 2) 현재 검증 완료된 핵심 운영 로직 보호
required = [
    ('06_Indicator.js', 'function resetIndicatorRoomCleaningFast_', '청소초기화 고속 경로'),
    ('19_RoommaidCloseJournal.js', 'SCHEMA_VERSION: 28', '룸메이드 마감 스키마 28'),
    ('19_RoommaidCloseJournal.js', 'const isOpeningStockReturn = NOVA_ROOMMAID_CLOSE.INITIAL_STOCK_STATUSES.includes(nextStatus)', '전일재고 복귀 판정'),
    ('19_RoommaidCloseJournal.js', 'restoredOpeningStock.canceled = false;', '전일재고 주기 복구'),
    ('19_RoommaidCloseJournal.js', 'activeByRoom[roomNo] = restoredOpeningStock;', '복구 주기 활성화'),
    ('08_Telegram.js', "getProperty('TELEGRAM_BOT_TOKEN')", 'Telegram Bot Token Script Property'),
    ('08_Telegram.js', 'function setupNovaTelegramConnection', 'Telegram 연결 설정'),
    ('Client.html', 'function novaRealtimeRoomChangesFetch_', 'Realtime room changes client'),
]
for path, marker, label in required:
    require_marker(path, marker, label)

# 3) 임시 진단/수동 복구 코드와 비밀값 유출 방지
forbidden_markers = {
    'checkNovaWebAppUrl': '임시 URL 진단 함수',
    'repairNovaTelegramWebhook': '임시 Telegram 복구 함수',
    '재고정합 진단': '임시 재고정합 진단 문구',
}
for p in ROOT.glob('*'):
    if not p.is_file() or p.suffix.lower() not in {'.js', '.html', '.gs'}:
        continue
    text = p.read_text(encoding='utf-8', errors='ignore')
    for marker, label in forbidden_markers.items():
        if marker in text:
            errors.append(f'{label}가 운영 소스에 남아 있습니다: {p.name}')

# Telegram bot token 형태의 실값이 저장소에 들어가는 것을 차단한다.
secret_pattern = re.compile(r'\b\d{7,12}:[A-Za-z0-9_-]{30,}\b')
for p in ROOT.rglob('*'):
    if not p.is_file() or '.git' in p.parts:
        continue
    if p.name == 'validate_nova_release.py':
        continue
    if p.suffix.lower() not in {'.js', '.html', '.gs', '.json', '.yml', '.yaml', '.py'}:
        continue
    text = p.read_text(encoding='utf-8', errors='ignore')
    if secret_pattern.search(text):
        errors.append(f'비밀값으로 보이는 Telegram token이 저장소에 포함되어 있습니다: {p.relative_to(ROOT)}')

# 4) Apps Script 서버 JS 문법 검사
js_files = sorted(p for p in ROOT.glob('*.js') if p.is_file())
for p in js_files:
    result = subprocess.run(['node', '--check', str(p)], text=True, capture_output=True)
    if result.returncode != 0:
        errors.append(f'JS 문법 오류: {p.name}\n{result.stderr.strip()}')
notes.append(f'Node syntax checked: {len(js_files)} files')

if errors:
    print('NOVA RELEASE VALIDATION: FAIL')
    for item in errors:
        print(f'- {item}')
    sys.exit(1)

print('NOVA RELEASE VALIDATION: PASS')
for item in notes:
    print(f'- {item}')
print('- Protected: cleaning reset fast path, roommaid close schema 28/opening-stock restore, Telegram token property, Realtime client')
print('- Secret scan: PASS')
