from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
close_path = ROOT / '19_RoommaidCloseJournal.js'
daily_path = ROOT / '14_DailyClose.js'

close_text = close_path.read_text(encoding='utf-8')
daily_text = daily_path.read_text(encoding='utf-8')

# 1) Bump journal schema so previously saved close journals are treated as stale and recalculated.
old_schema = "  SCHEMA_VERSION: 26,"
new_schema = "  SCHEMA_VERSION: 27,"
if close_text.count(old_schema) != 1:
    raise SystemExit(f'PATCH_ERROR: expected schema anchor once, found {close_text.count(old_schema)}')
close_text = close_text.replace(old_schema, new_schema, 1)

# 2) Preserve true opening stock classification when it changes to a departure status before completion.
#    Previously the same cycle was reclassified from initialStock -> departure, which could make the
#    close journal's opening stock count smaller than the upload/indicator opening stock count.
old_cycle = """        if (active && !active.completed && !active.canceled && (active.initialStock || active.departure)) {
          active.initialStock = false;
          active.manualInitialStock = false;
          active.departure = true;
          active.bucket = nextBucket;
          active.sourceStatus = nextStatus;
          active.reclassifiedVersion = item.version;
          active.reclassifiedAt = item.eventAt;
        } else {
"""
new_cycle = """        if (active && !active.completed && !active.canceled && (active.initialStock || active.departure)) {
          const openingInitialStock = Boolean(active.initialStock && !active.manualInitialStock);
          if (openingInitialStock) {
            // 최종 객실현황 업로드에서 시작한 전일재고는 당일 퇴실상태로 바뀌어도
            // 같은 미완료 정비주기 동안 전일재고 원천분류를 유지한다.
            // 그래야 통합 인디게이터/업로드의 전일재고와 마감일지 전일재고가 어긋나지 않는다.
            active.initialStock = true;
            active.departure = false;
          } else {
            // 당일 수동 재고 또는 기존 퇴실주기는 기존 동작대로 최종 퇴실분류를 따른다.
            active.initialStock = false;
            active.manualInitialStock = false;
            active.departure = true;
          }
          active.bucket = nextBucket;
          active.sourceStatus = nextStatus;
          active.reclassifiedVersion = item.version;
          active.reclassifiedAt = item.eventAt;
        } else {
"""
if close_text.count(old_cycle) != 1:
    raise SystemExit(f'PATCH_ERROR: expected stock/departure cycle anchor once, found {close_text.count(old_cycle)}')
close_text = close_text.replace(old_cycle, new_cycle, 1)

# 3) Actually run the already-existing integrity validator before saving a close snapshot.
old_save = """function saveDailyCloseSnapshotForSite_(businessDate, site, user, preloaded) { // (사업장별 마감 스냅샷 저장)
  const closedAt = nowText_();
  const preload = preloaded || {};
  const snapshot = buildDailyCloseSnapshot_(businessDate, site, {
    closedBy: user.employeeNo,
    closedByName: user.name,
    closedAt,
    includeRooms: true,
    currentRows: preload.currentRows,
    historyRows: preload.historyRows,
    attendanceEmployeeNos: preload.attendanceEmployeeNos
  });
"""
new_save = """function saveDailyCloseSnapshotForSite_(businessDate, site, user, preloaded) { // (사업장별 마감 스냅샷 저장)
  const closedAt = nowText_();
  const preload = preloaded || {};
  const currentRows = Array.isArray(preload.currentRows)
    ? preload.currentRows
    : readCurrentRowsForClose_(businessDate, site);
  const historyRows = Array.isArray(preload.historyRows)
    ? preload.historyRows
    : readHistoryRowsForClose_(businessDate, site);

  // 저장 전에 현재객실·업로드기준·정비주기 정합을 강제 검증한다.
  // 숫자가 맞지 않는 상태를 그대로 DAILY_CLOSE로 확정 저장하지 않는다.
  validateRoommaidCloseIntegrityForSave_(businessDate, site, currentRows, historyRows);

  const snapshot = buildDailyCloseSnapshot_(businessDate, site, {
    closedBy: user.employeeNo,
    closedByName: user.name,
    closedAt,
    includeRooms: true,
    currentRows,
    historyRows,
    attendanceEmployeeNos: preload.attendanceEmployeeNos
  });
"""
if daily_text.count(old_save) != 1:
    raise SystemExit(f'PATCH_ERROR: expected daily-close save anchor once, found {daily_text.count(old_save)}')
daily_text = daily_text.replace(old_save, new_save, 1)

# Sanity checks.
checks = [
    ("SCHEMA_VERSION: 27", close_text),
    ("const openingInitialStock = Boolean(active.initialStock && !active.manualInitialStock);", close_text),
    ("validateRoommaidCloseIntegrityForSave_(businessDate, site, currentRows, historyRows);", daily_text),
]
for needle, haystack in checks:
    if needle not in haystack:
        raise SystemExit(f'VERIFY_ERROR: missing {needle}')

close_path.write_text(close_text, encoding='utf-8')
daily_path.write_text(daily_text, encoding='utf-8')

print('PATCH_OK')
print('Repository only; production Apps Script NOT changed yet')
print('Changed: 19_RoommaidCloseJournal.js, 14_DailyClose.js')
print('Fixed: opening-stock cycle no longer becomes same-day departure before completion')
print('Added: close-save integrity validation using existing validator')
print('Schema: roommaid close journal 26 -> 27 so saved old journal recalculates')
print('Preserved: completion counting, personal performance, RC/HU buckets, realtime cleaning-reset mirror, UI/layout')
print('VERIFY: PASS')
