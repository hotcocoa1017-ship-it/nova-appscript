from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "19_RoommaidCloseJournal.js"
text = TARGET.read_text(encoding="utf-8")

old = """    const selected = useSaved ? saved : liveSnapshot;\n    const journal = selected.roommaidCloseJournal || liveSnapshot.roommaidCloseJournal;\n\n    return {\n"""
new = """    const selected = useSaved ? saved : liveSnapshot;\n    const journal = selected.roommaidCloseJournal || liveSnapshot.roommaidCloseJournal;\n    const stockDiagnostic = buildRoommaidCloseStockDiagnostic_(businessDate, preferredSite, currentRows, historyRows);\n    const baseWarning = journal && journal.initialStatusDetailAvailable\n      ? ''\n      : '해당 업무일자의 객실현황 업로드가 RC6.4 이전에 적용되어 최초 재고·퇴실의 객실별 상세가 없습니다. 현재 상태를 기준으로 보정 표시됩니다.';\n\n    return {\n"""
if text.count(old) != 1:
    raise SystemExit(f"PATCH_ERROR: getRoommaidCloseJournal anchor expected 1, found {text.count(old)}")
text = text.replace(old, new, 1)

old_warning = """      warning: journal && journal.initialStatusDetailAvailable\n        ? ''\n        : '해당 업무일자의 객실현황 업로드가 RC6.4 이전에 적용되어 최초 재고·퇴실의 객실별 상세가 없습니다. 현재 상태를 기준으로 보정 표시됩니다.',\n"""
new_warning = """      warning: [baseWarning, stockDiagnostic.message].filter(Boolean).join(' / '),\n      stockDiagnostic,\n"""
if text.count(old_warning) != 1:
    raise SystemExit(f"PATCH_ERROR: warning anchor expected 1, found {text.count(old_warning)}")
text = text.replace(old_warning, new_warning, 1)

anchor = """function buildRoommaidCloseJournal_(businessDate, site, currentRows, historyRows, users, attendanceEmployeeNos) { // (현재객실현황 최신 1행·현재 분류 기준 마감일지 집계)\n"""
helper = r'''function buildRoommaidCloseStockDiagnostic_(businessDate, site, currentRows, historyRows) { // (인디게이터 재고 vs 마감 전일재고 객실단위 진단)
  const liveCurrentRows = latestRoommaidCloseCurrentRows_(currentRows || [], site);
  const master = readRoomMasterIndexForClose_(site);
  const upload = latestUploadSummaryForClose_(historyRows || []);
  const initialMap = buildInitialRoomStatusMapForClose_(upload, liveCurrentRows);
  const completionEvents = cleaningCompletionEventsForClose_(historyRows || []);
  const workloadHistoryRows = roommaidCloseHistoryAfterLatestUpload_(historyRows || [], upload);
  const workloadEvents = buildRoommaidCloseWorkloadEvents_(
    initialMap, workloadHistoryRows, completionEvents, master, liveCurrentRows, site
  );
  const normalizer = buildRoommaidCloseRoomStatusNormalizer_();

  const currentByRoom = {};
  liveCurrentRows.forEach(data => {
    const roomNo = normalizeRoomNo_(data && data['객실번호']);
    if (roomNo) currentByRoom[roomNo] = data;
  });

  const indicatorByBuilding = {};
  liveCurrentRows.forEach(data => {
    const roomNo = normalizeRoomNo_(data && data['객실번호']);
    if (!roomNo) return;
    const status = normalizeRoommaidCloseRoomStatus_(data && data['객실상태'], normalizer);
    // 통합 인디게이터의 '재고' 필터 숫자는 원본 roomStatus=STOCK 기준이다.
    if (status !== 'STOCK') return;
    const building = normalizeRoomBuilding_(data && data['동'], roomNo) || roomCloseMeta_(master, liveCurrentRows, site, roomNo).building || '미지정';
    if (!indicatorByBuilding[building]) indicatorByBuilding[building] = new Set();
    indicatorByBuilding[building].add(roomNo);
  });

  const closeByBuilding = {};
  (workloadEvents || []).forEach(event => {
    if (!event || !event.initialStock || event.canceled) return;
    const bucket = String(event.bucket || 'BUILDING').trim().toUpperCase();
    // 룸메이드 마감표의 동별 전일재고 칸에는 일반재고만 들어가고 RC/HU는 별도 칸이다.
    if (bucket !== 'BUILDING') return;
    const roomNo = normalizeRoomNo_(event.roomNo);
    if (!roomNo) return;
    const meta = roomCloseMeta_(master, liveCurrentRows, site, roomNo);
    const building = String(event.building || meta.building || '미지정').trim();
    if (!closeByBuilding[building]) closeByBuilding[building] = new Set();
    closeByBuilding[building].add(roomNo);
  });

  const buildings = Array.from(new Set(Object.keys(indicatorByBuilding).concat(Object.keys(closeByBuilding))))
    .sort(compareDailyCloseBuilding_);
  const mismatches = [];
  buildings.forEach(building => {
    const indicatorRooms = indicatorByBuilding[building] || new Set();
    const closeRooms = closeByBuilding[building] || new Set();
    if (indicatorRooms.size === closeRooms.size && [...indicatorRooms].every(roomNo => closeRooms.has(roomNo))) return;
    const indicatorOnly = [...indicatorRooms].filter(roomNo => !closeRooms.has(roomNo)).sort();
    const closeOnly = [...closeRooms].filter(roomNo => !indicatorRooms.has(roomNo)).sort();
    mismatches.push({
      building,
      indicatorCount: indicatorRooms.size,
      closeCount: closeRooms.size,
      indicatorOnly,
      closeOnly
    });
  });

  const describe = roomNo => {
    const initialStatus = normalizeRoommaidCloseRoomStatus_(initialMap[roomNo] || '', normalizer) || '없음';
    const currentStatus = normalizeRoommaidCloseRoomStatus_(currentByRoom[roomNo] && currentByRoom[roomNo]['객실상태'], normalizer) || '없음';
    return `${roomNo}(업로드:${initialStatus}→현재:${currentStatus})`;
  };

  const message = mismatches.length
    ? `재고정합 진단 ${mismatches.map(item => {
        const extra = item.indicatorOnly.length ? ` · 인디게이터에만 ${item.indicatorOnly.map(describe).join(',')}` : '';
        const missing = item.closeOnly.length ? ` · 마감에만 ${item.closeOnly.map(describe).join(',')}` : '';
        return `${item.building} 인디게이터 ${item.indicatorCount} / 마감 전일재고 ${item.closeCount}${extra}${missing}`;
      }).join(' | ')}`
    : '';

  return { businessDate, site, mismatches, message };
}

'''
if text.count(anchor) != 1:
    raise SystemExit(f"PATCH_ERROR: helper anchor expected 1, found {text.count(anchor)}")
text = text.replace(anchor, helper + anchor, 1)

TARGET.write_text(text, encoding="utf-8")

# verification
out = TARGET.read_text(encoding="utf-8")
checks = [
    "buildRoommaidCloseStockDiagnostic_",
    "stockDiagnostic = buildRoommaidCloseStockDiagnostic_",
    "warning: [baseWarning, stockDiagnostic.message]",
    "stockDiagnostic,",
    "status !== 'STOCK'",
    "bucket !== 'BUILDING'",
]
missing = [item for item in checks if item not in out]
if missing:
    raise SystemExit("VERIFY_ERROR: " + ", ".join(missing))

print("PATCH_OK")
print("Repository only; production Apps Script NOT changed yet")
print("Changed: 19_RoommaidCloseJournal.js only")
print("Added: read-only stock mismatch diagnostic in existing close-journal warning area")
print("Compares: indicator raw STOCK rooms vs close-journal BUILDING initial-stock rooms by room number")
print("No count/save/realtime logic changed")
print("VERIFY: PASS")
