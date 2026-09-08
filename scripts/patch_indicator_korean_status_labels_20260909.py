from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
marker = 'INDICATOR_KOREAN_STATUS_FALLBACK_V1'

if marker in text:
    print('Korean status fallback already applied.')
    raise SystemExit(0)

anchor = """  function indicatorCycleCleaningLabel_(cycle) { // (정비주기별 청소상태 카드 전문표기)\n    const code = codeValue_(state.indicator.data?.codes?.cleaningStatuses, cycle?.cleaningStatus || 'WAITING').toUpperCase();\n    if (code === 'WAITING') return 'VD';\n    if (code === 'NOT_REQUIRED') return 'N/R';\n    if (code === 'ASSIGNED') return '배정';\n    if (code === 'CLEANING') return '청소중';\n    if (['COMPLETED', 'QM_COMPLETED'].includes(code)) return 'VC';\n    return codeLabel_(state.indicator.data?.codes?.cleaningStatuses, cycle?.cleaningStatus || 'WAITING');\n  }\n"""
replacement = """  function indicatorRoomStatusDisplayLabel_(value) { // INDICATOR_KOREAN_STATUS_FALLBACK_V1 · DB 영문코드 UI 한글표시 보장\n    const roomStatuses = state.indicator.data?.codes?.roomStatuses || [];\n    const raw = String(value || '').trim();\n    const code = indicatorCodeValue_(roomStatuses, raw).toUpperCase();\n    const configured = String(codeLabel_(roomStatuses, raw || code || '') || '').trim();\n    if (configured && configured.toUpperCase() !== code && configured !== raw) return configured;\n    const fallback = {\n      VACANT_CLEAN: '공실', STOCK: '재고', STOCK_RC: '재고 R/C', STOCK_HU: '재고 H/U',\n      STAY: '투숙', DUE_OUT: '퇴실예정', CHECKED_OUT: '퇴실', CHECKED_OUT_RC: '퇴실R/C',\n      CHECKED_OUT_HU: '퇴실H/U', RECHECKIN: '재입실'\n    };\n    return fallback[code] || configured || raw || '-';\n  }\n\n  function indicatorCleaningStatusDisplayLabel_(value) { // INDICATOR_KOREAN_STATUS_FALLBACK_V1\n    const cleaningStatuses = state.indicator.data?.codes?.cleaningStatuses || [];\n    const raw = String(value || '').trim();\n    const code = indicatorCodeValue_(cleaningStatuses, raw).toUpperCase();\n    const configured = String(codeLabel_(cleaningStatuses, raw || code || '') || '').trim();\n    if (configured && configured.toUpperCase() !== code && configured !== raw) return configured;\n    const fallback = {\n      WAITING: '대기', NOT_REQUIRED: '정비대상 아님', ASSIGNED: '배정', CLEANING: '청소중',\n      COMPLETED: '청소완료', QM_WAITING: 'QM대기', QM_CHECKING: 'QM점검중',\n      QM_COMPLETED: 'QM완료', REWORK: '재정비'\n    };\n    return fallback[code] || configured || raw || '-';\n  }\n\n  function indicatorCycleCleaningLabel_(cycle) { // (정비주기별 청소상태 카드 전문표기)\n    const code = codeValue_(state.indicator.data?.codes?.cleaningStatuses, cycle?.cleaningStatus || 'WAITING').toUpperCase();\n    if (code === 'WAITING') return 'VD';\n    if (code === 'NOT_REQUIRED') return 'N/R';\n    if (code === 'ASSIGNED') return '배정';\n    if (code === 'CLEANING') return '청소중';\n    if (['COMPLETED', 'QM_COMPLETED'].includes(code)) return 'VC';\n    return indicatorCleaningStatusDisplayLabel_(cycle?.cleaningStatus || code || 'WAITING');\n  }\n"""
if anchor not in text:
    raise SystemExit('ERROR: cleaning label anchor not found')
text = text.replace(anchor, replacement, 1)

old = """    const roomStatusLabel = codeLabel_(roomStatuses, roomStatusCode || source.roomStatus || room.roomStatus || '');\n"""
new = """    const roomStatusLabel = indicatorRoomStatusDisplayLabel_(roomStatusCode || source.roomStatus || room.roomStatus || '');\n"""
if old not in text:
    raise SystemExit('ERROR: room status label anchor not found')
text = text.replace(old, new, 1)

required = [marker, "VACANT_CLEAN: '공실'", "DUE_OUT: '퇴실예정'", "CHECKED_OUT_RC: '퇴실R/C'", "QM_WAITING: 'QM대기'", "indicatorRoomStatusDisplayLabel_(roomStatusCode"]
for needle in required:
    if needle not in text:
        raise SystemExit(f'ERROR: missing {needle}')

path.write_text(text, encoding='utf-8')
print('Applied Korean status display fallback.')
