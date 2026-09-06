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

# 관리자/오더테이커 QM 배정 초기화 + 객실조치 재정비 버튼은
# 매 배포에서 동일하게 보장합니다. Client와 06_Indicator를 최소범위로 패치합니다.
subprocess.run([sys.executable, 'scripts/patch_qm_clear_rework_controls_20260905.py'], check=True)

# DB-first 대량처리에서 1,500 START + 1,500 COMPLETE 이벤트가 한 번에 몰려도
# 기존 500건 단위 Sheet 미러를 최대 6페이지까지 한 예약실행에서 배수하도록 보장합니다.
subprocess.run([sys.executable, 'scripts/patch_realtime_event_drain_3000_v1.py'], check=True)

# QM 하우스맨 요청은 PostgreSQL에서 먼저 확정하고 Sheet/Telegram은 후행 미러합니다.
# 권한/검증/결과불명 오류에서는 legacy Sheet로 이중쓰기하지 않도록 전용 검증까지 즉시 실행합니다.
subprocess.run([sys.executable, 'scripts/patch_qm_houseman_dbfirst_20260906.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_qm_houseman_dbfirst_20260906.py'], check=True)
