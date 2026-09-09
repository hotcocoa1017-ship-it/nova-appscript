from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
original = text
marker = 'ROOM_LAST_QM_CARD_V1'

# 1) Small, neutral inline label beside the room number.
style_anchor = "\n</style>\n<script>"
style_block = """

  /* ROOM_LAST_QM_CARD_V1 · 객실번호 옆 마지막 유효 QM 점검일 */
  .room-last-qm-check {
    margin-left: 7px;
    color: #6b7280;
    font-size: 10px;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.2px;
    white-space: nowrap;
  }
  @media (max-width: 760px) {
    .room-last-qm-check { margin-left: 6px; font-size: 11px; }
  }
"""
if marker not in text:
    if style_anchor not in text:
        raise SystemExit('ERROR: Client style/script anchor not found')
    text = text.replace(style_anchor, style_block + style_anchor, 1)

# 2) DB authority field list: keep Sheet delta from wiping the two auxiliary DB fields.
old_fields = "'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'cleaningStartedAt', 'cleaningCompletedAt', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'"
new_fields = "'cleaningStatus', 'cleaningType', 'assignmentType', 'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo', 'cleaningStartedAt', 'cleaningCompletedAt', 'lastQmBusinessDate', 'lastQmEmployeeNo', 'operationalStatus', 'preassigned', 'vip', 'importantRoom', 'version', 'updatedAt'"
if new_fields not in text:
    if old_fields not in text:
        raise SystemExit('ERROR: realtime room field anchor not found')
    text = text.replace(old_fields, new_fields, 1)

# 3) Full /v1/rooms mapper. Cloud Run already SELECT * from nova_rooms_current.
old_full = "      cleaningStartedAt: row.cleaning_started_at || row.cleaningStartedAt || '',\n      cleaningCompletedAt: row.cleaning_completed_at || row.cleaningCompletedAt || '',\n      operationalStatus: String(row.operational_status ?? row.operationalStatus ?? ''),"
new_full = "      cleaningStartedAt: row.cleaning_started_at || row.cleaningStartedAt || '',\n      cleaningCompletedAt: row.cleaning_completed_at || row.cleaningCompletedAt || '',\n      lastQmBusinessDate: String(row.last_qm_business_date ?? row.lastQmBusinessDate ?? ''),\n      lastQmEmployeeNo: String(row.last_qm_employee_no ?? row.lastQmEmployeeNo ?? ''),\n      operationalStatus: String(row.operational_status ?? row.operationalStatus ?? ''),"
if new_full not in text:
    if old_full not in text:
        raise SystemExit('ERROR: full room mapper anchor not found')
    text = text.replace(old_full, new_full, 1)

# 4) Realtime Broadcast partial mapper.
old_partial = "    putText('cleaningStartedAt', 'cleaning_started_at', 'cleaningStartedAt');\n    putText('cleaningCompletedAt', 'cleaning_completed_at', 'cleaningCompletedAt');\n    putText('operationalStatus', 'operational_status', 'operationalStatus');"
new_partial = "    putText('cleaningStartedAt', 'cleaning_started_at', 'cleaningStartedAt');\n    putText('cleaningCompletedAt', 'cleaning_completed_at', 'cleaningCompletedAt');\n    putText('lastQmBusinessDate', 'last_qm_business_date', 'lastQmBusinessDate');\n    putText('lastQmEmployeeNo', 'last_qm_employee_no', 'lastQmEmployeeNo');\n    putText('operationalStatus', 'operational_status', 'operationalStatus');"
if new_partial not in text:
    if old_partial not in text:
        raise SystemExit('ERROR: partial room mapper anchor not found')
    text = text.replace(old_partial, new_partial, 1)

# 5) Only display on unsold/currently vacant inventory states. The text itself stays minimal.
status_anchor = """  function indicatorRoomCardStatusLabel_(room) { // (검색용 현재 정비주기 상태명)
    return indicatorRoomCycleView_(room, false).label;
  }

  function roomCardHtml_(room) { // (객실카드 HTML·당일 최대 2개 정비주기 표시)
"""
status_new = """  function indicatorRoomCardStatusLabel_(room) { // (검색용 현재 정비주기 상태명)
    return indicatorRoomCycleView_(room, false).label;
  }

  function indicatorLastQmDisplayDate_(room) { // ROOM_LAST_QM_CARD_V1 · 미판매 유지 객실의 마지막 유효 점검일
    const value = String(room?.lastQmBusinessDate || '').trim();
    if (!value) return '';
    const roomStatusCode = indicatorCodeValue_(state.indicator.data?.codes?.roomStatuses, room?.roomStatus || '').toUpperCase();
    if (!['VACANT_CLEAN', 'STOCK', 'STOCK_RC', 'STOCK_HU'].includes(roomStatusCode)) return '';
    const matched = value.match(/^(\\d{4})-(\\d{2})-(\\d{2})/);
    return matched ? `${matched[2]}/${matched[3]}` : '';
  }

  function roomCardHtml_(room) { // (객실카드 HTML·당일 최대 2개 정비주기 표시)
"""
if 'function indicatorLastQmDisplayDate_' not in text:
    if status_anchor not in text:
        raise SystemExit('ERROR: room card helper anchor not found')
    text = text.replace(status_anchor, status_new, 1)

old_card_vars = """    const currentCycle = indicatorRoomCycleView_(room, false);
    const previousCycle = room.previousCycle ? indicatorRoomCycleView_(room, true) : null;
    const cleaningActive = isCleaningActiveStatus_(room.cleaningStatus, state.indicator.data?.codes?.cleaningStatuses)
"""
new_card_vars = """    const currentCycle = indicatorRoomCycleView_(room, false);
    const previousCycle = room.previousCycle ? indicatorRoomCycleView_(room, true) : null;
    const lastQmDisplayDate = indicatorLastQmDisplayDate_(room);
    const cleaningActive = isCleaningActiveStatus_(room.cleaningStatus, state.indicator.data?.codes?.cleaningStatuses)
"""
if new_card_vars not in text:
    if old_card_vars not in text:
        raise SystemExit('ERROR: room card variable anchor not found')
    text = text.replace(old_card_vars, new_card_vars, 1)

old_title = """          <div class=\"room-card-title\"><span class=\"room-number\">${escapeHtml(room.roomNo)}</span>${operationalStatusLabel ? `<span class=\"room-card-operational-label ${escapeAttr(operationalStatusClass)}\">${escapeHtml(operationalStatusLabel)}</span>` : ''}</div>
"""
new_title = """          <div class=\"room-card-title\"><span class=\"room-number\">${escapeHtml(room.roomNo)}</span>${lastQmDisplayDate ? `<span class=\"room-last-qm-check\">최종점검 ${escapeHtml(lastQmDisplayDate)}</span>` : ''}${operationalStatusLabel ? `<span class=\"room-card-operational-label ${escapeAttr(operationalStatusClass)}\">${escapeHtml(operationalStatusLabel)}</span>` : ''}</div>
"""
if new_title not in text:
    if old_title not in text:
        raise SystemExit('ERROR: room card title anchor not found')
    text = text.replace(old_title, new_title, 1)

required = [
    'ROOM_LAST_QM_CARD_V1',
    "'lastQmBusinessDate', 'lastQmEmployeeNo'",
    "lastQmBusinessDate: String(row.last_qm_business_date",
    "putText('lastQmBusinessDate', 'last_qm_business_date', 'lastQmBusinessDate');",
    'function indicatorLastQmDisplayDate_',
    "['VACANT_CLEAN', 'STOCK', 'STOCK_RC', 'STOCK_HU']",
    '최종점검 ${escapeHtml(lastQmDisplayDate)}',
]
for needle in required:
    if needle not in text:
        raise SystemExit(f'ERROR: required marker missing: {needle}')

if text == original:
    print('ROOM_LAST_QM_CARD_V1 already applied; no source change needed.')
else:
    path.write_text(text, encoding='utf-8')
    print('Applied ROOM_LAST_QM_CARD_V1 client patch.')
