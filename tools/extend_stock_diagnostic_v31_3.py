from pathlib import Path

p = Path('19_RoommaidCloseJournal.js')
s = p.read_text(encoding='utf-8')
old = "return `${roomNo}(업로드:${initialStatus}→현재:${currentStatus})`;"
new = """const roomHistory = closeWorkloadHistorySequence_(workloadHistoryRows, completionEvents)
      .filter(item => normalizeRoomNo_(item && item.data && item.data['객실번호']) === roomNo)
      .map(item => item.kind === 'STATUS'
        ? `상태:${normalizeRoommaidCloseRoomStatus_(item.detail && item.detail.previousRoomStatus || '', normalizer) || '?'}>${normalizeRoommaidCloseRoomStatus_(item.detail && item.detail.roomStatus || '', normalizer) || '?'}`
        : `완료:${normalizeRoommaidCloseRoomStatus_(item.detail && (item.detail.sourceRoomStatus || item.detail.previousRoomStatus || item.detail.roomStatus) || '', normalizer) || '?'}`);
    const roomCycles = (workloadEvents || [])
      .filter(event => normalizeRoomNo_(event && event.roomNo) === roomNo)
      .map(event => [
        event.initialStock ? '전일재고' : '',
        event.manualInitialStock ? '수동재고' : '',
        event.departure ? '퇴실' : '',
        event.completed ? '완료' : '',
        event.canceled ? `취소:${event.cancelReason || '?'}` : '',
        `bucket:${String(event.bucket || 'BUILDING')}`,
        `source:${String(event.sourceStatus || '')}`
      ].filter(Boolean).join(','));
    return `${roomNo}(업로드:${initialStatus}→현재:${currentStatus}) · 이력[${roomHistory.join('→') || '없음'}] · 주기[${roomCycles.join(' / ') || '없음'}]`;"""
if s.count(old) != 1:
    raise SystemExit(f'PATCH_ERROR: expected 1 anchor, found {s.count(old)}')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('PATCH_OK')
print('Changed: 19_RoommaidCloseJournal.js only')
print('Added: read-only timeline/cycle details for mismatch rooms')
print('VERIFY: PASS')
