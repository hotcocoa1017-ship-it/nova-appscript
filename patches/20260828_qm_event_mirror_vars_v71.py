from pathlib import Path
p=Path(__file__).resolve().parents[1]/'RealtimeDailySync.js'
s=p.read_text(encoding='utf-8')
repls={
"businessDate: recordBusinessDate,":"businessDate: eventBusinessDate,",
"site: String(rowInfo.data['사업장'] || site).trim(),\n            roomNo,":"site: eventSite,\n            roomNo: eventRoomNo,",
"startedAt: eventTime || nowText_(),":"startedAt: String(event.eventTime || '').trim() || nowText_(),",
"              dbRoomVersion,\n              dbEventTime: eventTime || ''":"              dbRoomVersion: Number(event.roomVersion || 0),\n              dbEventTime: String(event.eventTime || '')"
}
for a,b in repls.items():
    if s.count(a)!=1: raise SystemExit(f'PATCH_ERROR expected one match: {a}')
    s=s.replace(a,b,1)
p.write_text(s,encoding='utf-8')
print('QM_EVENT_MIRROR_V71_OK')
print('Changed: RealtimeDailySync.js only')
