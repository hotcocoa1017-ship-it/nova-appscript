from pathlib import Path

path = Path('Client.html')
text = path.read_text(encoding='utf-8')
original = text
marker = 'QM_LAST_QM_MOBILE_CARD_V1'

# 1) Add one read-only helper/cache for QM browse cards and one shared display formatter.
anchor = """  function renderQmBrowseTabs_() { // (QM 점검대상·당일청소완료·공실 탭)\n"""
helper = """  // QM_LAST_QM_MOBILE_CARD_V1 · QM 모바일 카드의 마지막 유효 점검일 표시/추가조회 보조\n  const qmLastQmCardCache_ = new Map();\n\n  function mobileLastQmDisplayDate_(room) {\n    const value = String(room?.lastQmBusinessDate || room?.last_qm_business_date || '').trim();\n    if (!value) return '';\n    const roomStatus = String(room?.roomStatus || room?.room_status || '').trim().toUpperCase();\n    if (!['VACANT_CLEAN', 'STOCK', 'STOCK_RC', 'STOCK_HU'].includes(roomStatus)) return '';\n    const matched = value.match(/^(\\d{4})-(\\d{2})-(\\d{2})/);\n    return matched ? `${matched[2]}/${matched[3]}` : '';\n  }\n\n  async function novaQmLastQmCardMap_(businessDate, site, force = false) {\n    const safeDate = String(businessDate || '').trim();\n    const safeSite = String(site || '').trim();\n    if (!safeDate || !safeSite || !novaRealtimeIsEnabled_()) return new Map();\n    const cacheKey = `${safeDate}|${safeSite}`;\n    const cached = qmLastQmCardCache_.get(cacheKey);\n    if (!force && cached && Date.now() - Number(cached.cachedAt || 0) < 30000) return cached.map;\n\n    const auth = await novaQmDraftAuthBundle_();\n    if (!auth?.token || !auth?.supabaseUrl || !auth?.publishableKey) return new Map();\n    const response = await fetch(`${String(auth.supabaseUrl || '').replace(/\\/+$/, '')}/rest/v1/rpc/nova_qm_last_qm_cards_v1`, {\n      method: 'POST',\n      headers: {\n        'Content-Type': 'application/json',\n        'Authorization': `Bearer ${String(auth.token || '')}`,\n        'apikey': String(auth.publishableKey || '')\n      },\n      body: JSON.stringify({ p_business_date: safeDate, p_site: safeSite })\n    });\n    const data = await response.json().catch(() => ({}));\n    if (!response.ok || !data?.ok) {\n      const error = new Error(data?.message || data?.details || `QM 최종점검 조회 오류 (${response.status})`);\n      error.code = String(data?.code || '').trim();\n      throw error;\n    }\n    const map = new Map((Array.isArray(data.rooms) ? data.rooms : []).map(item => [\n      String(item?.roomNo || '').trim(),\n      {\n        lastQmBusinessDate: String(item?.lastQmBusinessDate || ''),\n        lastQmEmployeeNo: String(item?.lastQmEmployeeNo || '')\n      }\n    ]));\n    qmLastQmCardCache_.set(cacheKey, { cachedAt: Date.now(), map });\n    return map;\n  }\n\n  function renderQmBrowseTabs_() { // (QM 점검대상·당일청소완료·공실 탭)\n"""
if marker not in text:
    if anchor not in text:
        raise SystemExit('ERROR: QM browse tabs anchor not found')
    text = text.replace(anchor, helper, 1)

# 2) Enrich the delayed QM browse list from the narrow DB read RPC without changing the Sheet payload.
old_load = """      if (!result?.ok) throw new Error(result?.message || 'QM 객실목록을 불러오지 못했습니다.');\n      if (view !== qmMobileBrowseView_()) return;\n      state.mobile.qmBrowseData = {\n        key,\n        view,\n        rooms: Array.isArray(result.rooms) ? result.rooms : [],\n        summary: result.summary || {},\n        serverTime: result.serverTime || ''\n      };\n"""
new_load = """      if (!result?.ok) throw new Error(result?.message || 'QM 객실목록을 불러오지 못했습니다.');\n      if (view !== qmMobileBrowseView_()) return;\n      let browseRooms = Array.isArray(result.rooms) ? result.rooms : [];\n      try {\n        const lastQmMap = await novaQmLastQmCardMap_(\n          state.mobile.businessDate || state.bootstrap.app.businessDate,\n          state.mobile.site,\n          Boolean(options.force)\n        );\n        if (lastQmMap.size) {\n          browseRooms = browseRooms.map(room => Object.assign({}, room, lastQmMap.get(String(room?.roomNo || '').trim()) || {}));\n        }\n      } catch (lastQmError) {\n        console.warn('[NOVA QM] 최종점검일 보조조회 실패 · 기본 객실목록 유지:', lastQmError?.message || lastQmError);\n      }\n      state.mobile.qmBrowseData = {\n        key,\n        view,\n        rooms: browseRooms,\n        summary: result.summary || {},\n        serverTime: result.serverTime || ''\n      };\n"""
if new_load not in text:
    if old_load not in text:
        raise SystemExit('ERROR: QM browse load anchor not found')
    text = text.replace(old_load, new_load, 1)

# 3) Add the same minimal date beside room number in QM browse cards.
old_browse_vars = """  function renderQmBrowseRoomCard_(room, view) { // (QM 추가탭 카드 · 안전 본인확보 후 기존 체크리스트 연결)\n    const roomStatus = codeLabel_(state.mobile.data?.codes?.roomStatuses, room.roomStatus);\n    const cleaningStatus = codeLabel_(state.mobile.data?.codes?.cleaningStatuses, room.cleaningStatus);\n"""
new_browse_vars = """  function renderQmBrowseRoomCard_(room, view) { // (QM 추가탭 카드 · 안전 본인확보 후 기존 체크리스트 연결)\n    const roomStatus = codeLabel_(state.mobile.data?.codes?.roomStatuses, room.roomStatus);\n    const cleaningStatus = codeLabel_(state.mobile.data?.codes?.cleaningStatuses, room.cleaningStatus);\n    const lastQmDisplayDate = mobileLastQmDisplayDate_(room);\n"""
if new_browse_vars not in text:
    if old_browse_vars not in text:
        raise SystemExit('ERROR: QM browse card vars anchor not found')
    text = text.replace(old_browse_vars, new_browse_vars, 1)

old_browse_top = """      <div class=\"mobile-card-top\"><strong>${escapeHtml(room.roomNo)}</strong><span>${escapeHtml([room.building, room.floor ? `${room.floor}층` : ''].filter(Boolean).join(' · '))}</span></div>\n"""
new_browse_top = """      <div class=\"mobile-card-top\"><strong>${escapeHtml(room.roomNo)}${lastQmDisplayDate ? `<span class=\"room-last-qm-check\">최종점검 ${escapeHtml(lastQmDisplayDate)}</span>` : ''}</strong><span>${escapeHtml([room.building, room.floor ? `${room.floor}층` : ''].filter(Boolean).join(' · '))}</span></div>\n"""
if new_browse_top not in text:
    if old_browse_top not in text:
        raise SystemExit('ERROR: QM browse card top anchor not found')
    text = text.replace(old_browse_top, new_browse_top, 1)

# 4) Add the same minimal date to the normal QM target card. Other roles stay unchanged.
old_mobile_vars = """  function renderMobileRoomCard_(room, role) { // (룸메이드·QM·퍼블릭 모바일 객실 카드)\n    const roomStatus = codeLabel_(state.mobile.data.codes?.roomStatuses, room.roomStatus);\n    const cleaningStatus = codeLabel_(state.mobile.data.codes?.cleaningStatuses, room.cleaningStatus);\n"""
new_mobile_vars = """  function renderMobileRoomCard_(room, role) { // (룸메이드·QM·퍼블릭 모바일 객실 카드)\n    const roomStatus = codeLabel_(state.mobile.data.codes?.roomStatuses, room.roomStatus);\n    const cleaningStatus = codeLabel_(state.mobile.data.codes?.cleaningStatuses, room.cleaningStatus);\n    const lastQmDisplayDate = role === 'QM' ? mobileLastQmDisplayDate_(room) : '';\n"""
if new_mobile_vars not in text:
    if old_mobile_vars not in text:
        raise SystemExit('ERROR: mobile room card vars anchor not found')
    text = text.replace(old_mobile_vars, new_mobile_vars, 1)

# Replace only the first matching mobile top after renderMobileRoomCard_ by splitting around function.
func_marker = "  function renderMobileRoomCard_(room, role) {"
func_pos = text.find(func_marker)
if func_pos < 0:
    raise SystemExit('ERROR: renderMobileRoomCard_ not found')
func_end = text.find("\n  // QM_START_DB_FIRST_DIRECT_V1", func_pos)
if func_end < 0:
    raise SystemExit('ERROR: renderMobileRoomCard_ end anchor not found')
segment = text[func_pos:func_end]
old_mobile_top = """      <div class=\"mobile-card-top\"><strong>${escapeHtml(room.roomNo)}</strong><span>${escapeHtml([room.building, room.floor ? `${room.floor}층` : ''].filter(Boolean).join(' · '))}</span></div>\n"""
new_mobile_top = """      <div class=\"mobile-card-top\"><strong>${escapeHtml(room.roomNo)}${lastQmDisplayDate ? `<span class=\"room-last-qm-check\">최종점검 ${escapeHtml(lastQmDisplayDate)}</span>` : ''}</strong><span>${escapeHtml([room.building, room.floor ? `${room.floor}층` : ''].filter(Boolean).join(' · '))}</span></div>\n"""
if new_mobile_top not in segment:
    if old_mobile_top not in segment:
        raise SystemExit('ERROR: normal QM mobile card top anchor not found')
    segment = segment.replace(old_mobile_top, new_mobile_top, 1)
    text = text[:func_pos] + segment + text[func_end:]

required = [
    'QM_LAST_QM_MOBILE_CARD_V1',
    'function mobileLastQmDisplayDate_',
    'function novaQmLastQmCardMap_',
    'nova_qm_last_qm_cards_v1',
    'rooms: browseRooms',
    "const lastQmDisplayDate = role === 'QM' ? mobileLastQmDisplayDate_(room) : '';",
]
for needle in required:
    if needle not in text:
        raise SystemExit(f'ERROR: required marker missing: {needle}')

if text == original:
    print('QM_LAST_QM_MOBILE_CARD_V1 already applied; no source change needed.')
else:
    path.write_text(text, encoding='utf-8')
    print('Applied QM_LAST_QM_MOBILE_CARD_V1 client patch.')
