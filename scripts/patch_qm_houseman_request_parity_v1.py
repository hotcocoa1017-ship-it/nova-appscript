from pathlib import Path

MARKER = 'QM_HOUSEMAN_REQUEST_PARITY_V1'
client_path = Path('Client.html')
photo_path = Path('HousemanRequestPhoto.js')
client = client_path.read_text(encoding='utf-8')
photo = photo_path.read_text(encoding='utf-8')

if MARKER in client and MARKER in photo:
    print('QM houseman request parity V1 already applied.')
    raise SystemExit(0)

# Client: allow QM to use the same PostgreSQL-first houseman create path as ROOMMAID.
old = """  async function createRoommaidHousemanRequestFast_(payload) { // (룸메이드 오더 PostgreSQL 선확정·Sheet 후행)\n    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();\n    if (role !== 'ROOMMAID') {\n      const legacy = await callServer('createMobileHousemanRequest', state.token, payload);\n      return Object.assign({}, legacy || {}, { realtime: false, mirrorPromise: Promise.resolve(legacy) });\n    }"""
new = """  async function createRoommaidHousemanRequestFast_(payload) { // (ROOMMAID·QM 하우스맨 요청 PostgreSQL 선확정·Sheet 후행) // QM_HOUSEMAN_REQUEST_PARITY_V1\n    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();\n    if (!['ROOMMAID', 'QM'].includes(role)) {\n      const legacy = await callServer('createMobileHousemanRequest', state.token, payload);\n      return Object.assign({}, legacy || {}, { realtime: false, mirrorPromise: Promise.resolve(legacy) });\n    }"""
if old not in client:
    raise SystemExit('Fast houseman request role anchor not found')
client = client.replace(old, new, 1)

old = "requestSource: 'ROOMMAID',"
new = "requestSource: role, // QM_HOUSEMAN_REQUEST_PARITY_V1"
if old not in client:
    raise SystemExit('requestSource anchor not found')
client = client.replace(old, new, 1)

old = """      if (role !== 'ROOMMAID') {\n        closeModal();\n        await runMobileAction_('createMobileHousemanRequest', payload, event.currentTarget);\n        return;\n      }"""
new = """      if (!['ROOMMAID', 'QM'].includes(role)) { // QM_HOUSEMAN_REQUEST_PARITY_V1\n        closeModal();\n        await runMobileAction_('createMobileHousemanRequest', payload, event.currentTarget);\n        return;\n      }"""
if old not in client:
    raise SystemExit('Mobile request submit role anchor not found')
client = client.replace(old, new, 1)

# For QM only, if the Cloud Run create endpoint rejects/fails, preserve the existing legacy request path.
old = """    const realtime = await novaRealtimeCreateHousemanOrder_(realtimePayload);\n    const mirrorPayload = Object.assign({}, realtime.mirrorPayload || realtimePayload, {"""
new = """    let realtime;\n    try {\n      realtime = await novaRealtimeCreateHousemanOrder_(realtimePayload);\n    } catch (error) {\n      if (role !== 'QM') throw error;\n      console.warn('[NOVA QM] 하우스맨 DB 우선등록 실패 · 기존 모바일 요청으로 fallback', error);\n      const legacy = await callServer('createMobileHousemanRequest', state.token, Object.assign({}, payload || {}, {\n        requestSource: 'QM', createdFrom: 'MOBILE', assignmentMode: 'UNASSIGNED', handover: false\n      }));\n      return Object.assign({}, legacy || {}, { realtime: false, fallback: true, mirrorPromise: Promise.resolve(legacy) });\n    }\n    const mirrorPayload = Object.assign({}, realtime.mirrorPayload || realtimePayload, {"""
if old not in client:
    raise SystemExit('Realtime create anchor not found')
client = client.replace(old, new, 1)

# Photo module: ROOMMAID and QM share capability, upload, and ownership/source validation.
old = "enabled: role === 'ROOMMAID',"
new = "enabled: ['ROOMMAID', 'QM'].includes(role), // QM_HOUSEMAN_REQUEST_PARITY_V1"
if old not in photo:
    raise SystemExit('Photo capability anchor not found')
photo = photo.replace(old, new, 1)

old = """    const user = auth.user;\n    if (String(user.role || '').trim().toUpperCase() !== 'ROOMMAID') throw new Error('룸메이드 요청사진 등록 권한이 없습니다.');"""
new = """    const user = auth.user;\n    const role = String(user.role || '').trim().toUpperCase();\n    if (!['ROOMMAID', 'QM'].includes(role)) throw new Error('하우스맨 요청사진 등록 권한이 없습니다.'); // QM_HOUSEMAN_REQUEST_PARITY_V1"""
if old not in photo:
    raise SystemExit('Photo upload role anchor not found')
photo = photo.replace(old, new, 1)

old = "latestDetail.photoAttachedFrom = 'ROOMMAID_MOBILE';"
new = "latestDetail.photoAttachedFrom = `${role}_MOBILE`; // QM_HOUSEMAN_REQUEST_PARITY_V1"
if old not in photo:
    raise SystemExit('Photo attached source anchor not found')
photo = photo.replace(old, new, 1)

old = """  if (String(detail.createdFrom || '').trim().toUpperCase() !== 'MOBILE'\n      || String(detail.requestSource || '').trim().toUpperCase() !== 'ROOMMAID') {\n    throw new Error('룸메이드 모바일 요청에만 사진을 추가할 수 있습니다.');\n  }"""
new = """  const role = String(user.role || '').trim().toUpperCase();\n  const requestSource = String(detail.requestSource || '').trim().toUpperCase();\n  if (String(detail.createdFrom || '').trim().toUpperCase() !== 'MOBILE'\n      || !['ROOMMAID', 'QM'].includes(role)\n      || requestSource !== role) {\n    throw new Error('본인이 모바일에서 등록한 하우스맨 요청에만 사진을 추가할 수 있습니다.');\n  } // QM_HOUSEMAN_REQUEST_PARITY_V1"""
if old not in photo:
    raise SystemExit('Photo ownership/source anchor not found')
photo = photo.replace(old, new, 1)

# Safety checks: keep the existing public function names and role guards.
for required in [
    "createMobileHousemanRequest",
    "window.novaCreateRoommaidHousemanRequestFast_",
    "['ROOMMAID', 'QM'].includes(role)",
    "requestSource: role",
    "QM_HOUSEMAN_REQUEST_PARITY_V1",
]:
    if required not in client:
        raise SystemExit('Client safety marker missing: ' + required)
for required in [
    "getMobileHousemanRequestPhotoCapability",
    "uploadMobileHousemanRequestPhoto",
    "requestSource !== role",
    "QM_HOUSEMAN_REQUEST_PARITY_V1",
]:
    if required not in photo:
        raise SystemExit('Photo safety marker missing: ' + required)

client_path.write_text(client, encoding='utf-8')
photo_path.write_text(photo, encoding='utf-8')
print('Applied QM_HOUSEMAN_REQUEST_PARITY_V1')
