from pathlib import Path

src = Path('MonthlyDbFirstBridge.js').read_text(encoding='utf-8')

required = [
    'MONTHLY_QM_QUALITY_STATUS_V1',
    'nova_monthly_qm_quality_v1',
    'QM_QUALITY_PASS',
    'QM_QUALITY_FAIL',
    "const statusLabel = result === 'FAIL' ? '불량' : '양호';",
    "statusLabel: '점검중'",
    "['QM_START', 'QM_COMPLETE']",
    'monthlyQmQualityFailureText_',
    'monthlyQmQualityCompleted_',
    'buildMonthlyHistoryBundleDbFirst_',
]
for marker in required:
    if marker not in src:
        raise SystemExit(f'Missing monthly QM quality marker: {marker}')

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

# 완료된 객실만 기존 시작/완료 이벤트를 품질 판정 한 줄로 대체해야 한다.
if 'finalRoomKeys.has(monthlyQmQualityRoomKey_(item))' not in src:
    raise SystemExit('Missing final-inspection scoped event suppression')
if "statusCode === 'QM_START' && !finalRoomKeys.has" not in src:
    raise SystemExit('In-progress QM inspection must remain visible as 점검중')
if "result === 'FAIL' ? (failureText ? `불량 : ${failureText}` : '불량') : '양호'" not in src:
    raise SystemExit('FAIL/PASS display text does not match requested semantics')

print('monthly QM quality status v1 validation: OK')
