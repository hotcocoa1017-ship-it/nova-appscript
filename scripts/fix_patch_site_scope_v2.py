from pathlib import Path
import subprocess
import sys

path = Path('scripts/patch_site_scope_indicator_close_v2.py')
text = path.read_text(encoding='utf-8')
start_marker = '        # site control gets explicit options and query button.\n'
end_marker = '        # replace the two auto-query listeners with dirty-only behavior and explicit query listener.\n'
start = text.find(start_marker)
end = text.find(end_marker, start + 1)
if start < 0 or end < 0:
    print('Site-scope V2 patch source already fixed or anchors unavailable.')
else:
    replacement = '''        # site control gets explicit options and query button.\n        client = replace_once(\n            client,\n            '<select id="indicatorSite"><option value="">전체</option></select>',\n            '<select id="indicatorSite"><option value="">사업장 선택</option><option value="쏘라노">쏘라노</option><option value="별관">별관</option></select><button id="indicatorQueryButton" class="filter-button primary-inline" type="button">조회하기</button>',\n            'Indicator site select/query button'\n        )\n\n'''
    text = text[:start] + replacement + text[end:]
    path.write_text(text, encoding='utf-8')
    print('Fixed site-scope V2 patch source syntax.')

# 모바일 상단 조회조건 레이아웃과 로그인 안내문구는 site-scope 패치 이후에도
# 매 배포마다 동일하게 보장합니다. 패치 자체가 멱등성이므로 재실행해도 중복 적용되지 않습니다.
subprocess.run([sys.executable, 'scripts/patch_mobile_indicator_layout_v1.py'], check=True)
