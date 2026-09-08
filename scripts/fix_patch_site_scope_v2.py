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

# ROOMMAID 청소시작/완료와 인디게이터는 Broadcast + 경량 polling + 주기 전체 DB 보정의
# 3중 동기화로 수렴시킵니다. 네트워크 응답이 멈춰 actionInFlight가 고착되는 경로도 제한시간으로 해제합니다.
subprocess.run([sys.executable, 'scripts/patch_room_state_sync_hardening_20260906.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_room_state_sync_hardening_20260906.py'], check=True)

# QM 최종제출은 객실 QM_COMPLETED + 점검결과 + draft 완료 + Realtime 이벤트를
# PostgreSQL 단일 트랜잭션으로 확정한 뒤 기존 Sheet 상세이력을 후행 미러합니다.
# RPC 미배포처럼 DB 변경 전임이 확실한 경우만 기존 QM_COMPLETE 경로를 허용합니다.
subprocess.run([sys.executable, 'scripts/patch_qm_finalize_dbfirst_v2_20260907.py'], check=True)
subprocess.run([sys.executable, 'scripts/patch_qm_finalize_preflight_v2_20260907.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_qm_finalize_dbfirst_v2_20260907.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_qm_finalize_preflight_v2_20260907.py'], check=True)

# Whole-DB 전환: 근무조/담당동, 퇴실지연, 일마감, 월별조회, 룸메이드 리포팅.
# DB 원본 확정 전에는 legacy를 보존하고, DB write 결과가 불명확한 경우에는 Sheet 이중쓰기를 금지합니다.
subprocess.run([sys.executable, 'scripts/patch_shift_zone_dbfirst_v3_20260907.py'], check=True)
subprocess.run([sys.executable, 'scripts/patch_departure_delay_dbfirst_v3_20260907.py'], check=True)
subprocess.run([sys.executable, 'scripts/patch_daily_close_dbfirst_fallback_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/patch_monthly_daily_dbfirst_v2_20260907.py'], check=True)
subprocess.run([sys.executable, 'scripts/patch_roommaid_reporting_dbfirst_v2_20260907.py'], check=True)
subprocess.run([sys.executable, 'scripts/patch_roommaid_close_save_dbfirst_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_whole_db_transition_v2_20260908.py'], check=True)

# 관리자 운영설정은 PostgreSQL을 쓰기 권위로 사용하고 코드설정 Sheet는 호환 미러로 유지합니다.
# DB confirmed 이후 write 장애에서는 Sheet 단독저장으로 우회하지 않습니다.
subprocess.run([sys.executable, 'scripts/patch_admin_operation_settings_dbfirst_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_admin_operation_settings_dbfirst_v1_20260908.py'], check=True)

# 관리자 코드/명칭 중 안정형 8개 그룹은 PostgreSQL을 쓰기 권위로 사용합니다.
# 사업장/객실타입/직무 자동시드는 기존 Sheet authority를 보존하고, QM 정의는 다음 컷오버로 분리합니다.
subprocess.run([sys.executable, 'scripts/patch_admin_code_settings_dbfirst_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_admin_code_settings_dbfirst_v1_20260908.py'], check=True)

# QM 체크리스트/점검장소 정의도 동일 code master의 DB authority를 사용합니다.
# ADMIN/ORDER 관리권한과 QM 읽기권한을 보존하며 Sheet는 DB 확정 후 호환 미러입니다.
subprocess.run([sys.executable, 'scripts/patch_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/patch_qm_checklist_definition_shape_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_qm_checklist_definition_shape_v1_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_qm_checklist_codes_dbfirst_v1_20260908.py'], check=True)

# 통합 인디게이터 하우스맨 오더 UI: 객실카드 숫자뱃지는 실제 미완료 오더내용을 tooltip으로 표시하고,
# 객실/미완료/전체 요약 pill은 처리현황 목록 필터 버튼으로 동작하도록 보장합니다.
subprocess.run([sys.executable, 'scripts/patch_indicator_houseman_order_ui_20260908.py'], check=True)
subprocess.run([sys.executable, 'scripts/validate_indicator_houseman_order_ui_20260908.py'], check=True)
