from pathlib import Path

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
