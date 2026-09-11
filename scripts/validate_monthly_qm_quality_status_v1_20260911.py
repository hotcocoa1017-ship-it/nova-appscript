from pathlib import Path

src = Path('MonthlyDbFirstBridge.js').read_text(encoding='utf-8')
bridge = Path('DbFirstBridge.js').read_text(encoding='utf-8')

required = [
    'MONTHLY_QM_QUALITY_STATUS_V2',
    'MONTHLY_QM_STATUS_DISPLAY_V2',
    'nova_monthly_qm_quality_v1',
    'QM_QUALITY_PASS',
    'QM_QUALITY_FAIL',
    "const statusLabel = result === 'FAIL' ? '불량' : '양호';",
    "statusLabel: '점검중'",
    "['QM_START', 'QM_COMPLETE']",
    'monthlyQmQualityCompleted_',
    'buildMonthlyHistoryBundleDbFirst_',
    '최종정비자',
    '청소완료',
    'roommaidName',
    'secondaryRoommaidName',
    'cleaningCompletedAt',
]
for marker in required:
    if marker not in src:
        raise SystemExit(f'Missing monthly QM quality marker: {marker}')

# 신규 조회 RPC가 DB-first 허용목록에 반드시 등록되어야 한다.
if "'nova_monthly_qm_quality_v1'" not in bridge:
    raise SystemExit('nova_monthly_qm_quality_v1 is missing from DB-first RPC allowlist')

# 이 변경은 조회 표시 전용이어야 하며 객실 상태/재정비/점검 최종제출을 쓰지 않는다.
for forbidden in [
    'updateMobileRoomOperation',
    'nova_qm_inspection_finalize_v2',
    'QM_REWORK',
    'updateRowByHeaders_',
    'setValue(',
    'setValues(',
    'appendUnifiedHistory_',
]:
    if forbidden in src:
        raise SystemExit(f'Monthly QM quality bridge must stay read-only: {forbidden}')

# 완료된 객실만 기존 시작/완료 이벤트를 양호·불량 한 줄로 대체한다.
if 'finalRoomKeys.has(monthlyQmQualityRoomKey_(item))' not in src:
    raise SystemExit('Missing final-inspection scoped event suppression')
if "statusCode === 'QM_START' && !finalRoomKeys.has" not in src:
    raise SystemExit('In-progress QM inspection must remain visible as 점검중')
if "const detailText = `최종정비자 ${finalCleanerText} · 청소완료 ${cleaningCompletedAt || '-'}`;" not in src:
    raise SystemExit('QM work detail must show final cleaner and cleaning completion time')

print('monthly QM quality status v2 validation: OK')
