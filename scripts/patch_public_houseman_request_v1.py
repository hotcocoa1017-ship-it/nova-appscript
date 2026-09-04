from pathlib import Path
import re

MARKER = 'PUBLIC_HOUSEMAN_REQUEST_V1'
client_path = Path('Client.html')
mobile_path = Path('10_Mobile.js')
photo_server_path = Path('HousemanRequestPhoto.js')
photo_client_path = Path('HousemanRequestPhotoClient.html')

client = client_path.read_text(encoding='utf-8')
mobile = mobile_path.read_text(encoding='utf-8')
photo_server = photo_server_path.read_text(encoding='utf-8')
photo_client = photo_client_path.read_text(encoding='utf-8')

if all(MARKER in text for text in [client, mobile, photo_server, photo_client]):
    print('PUBLIC_HOUSEMAN_REQUEST_V1 already applied.')
    raise SystemExit(0)

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)

# ---------- Client.html ----------
client = replace_once(
    client,
    "  async function createRoommaidHousemanRequestFast_(payload) { // (ROOMMAID·QM 하우스맨 요청 PostgreSQL 선확정·Sheet 후행) // QM_HOUSEMAN_REQUEST_PARITY_V1\n    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();\n    if (!['ROOMMAID', 'QM'].includes(role)) {",
    "  async function createRoommaidHousemanRequestFast_(payload) { // (ROOMMAID·QM·PUBLIC 하우스맨 요청 PostgreSQL 선확정·Sheet 후행) // QM_HOUSEMAN_REQUEST_PARITY_V1 · PUBLIC_HOUSEMAN_REQUEST_V1\n    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();\n    if (!['ROOMMAID', 'QM', 'PUBLIC'].includes(role)) {",
    'fast request roles'
)

client = replace_once(
    client,
    "    const realtimePayload = Object.assign({}, payload || {}, {\n      assignmentMode: 'UNASSIGNED',\n      assignedEmployeeNo: '',\n      requester: state.bootstrap?.user?.name || '',\n      handover: false\n    });",
    "    let publicAssignment = null; // PUBLIC_HOUSEMAN_REQUEST_V1\n    if (role === 'PUBLIC') {\n      const assignmentResult = await callServer('getMobilePublicHousemanAutoAssignment', state.token, {\n        businessDate: payload?.businessDate, site: payload?.site, roomNo: payload?.roomNo\n      });\n      publicAssignment = assignmentResult?.assignment || null;\n      if (!publicAssignment?.employeeNo) throw new Error('해당 동에 자동배정 가능한 하우스맨이 없습니다.');\n    }\n    const realtimePayload = Object.assign({}, payload || {}, {\n      assignmentMode: role === 'PUBLIC' ? 'AUTO' : 'UNASSIGNED',\n      assignedEmployeeNo: '',\n      realtimeAssignmentSnapshot: publicAssignment,\n      requester: state.bootstrap?.user?.name || '',\n      handover: false\n    });",
    'public realtime assignment'
)

client = replace_once(
    client,
    "      if (role !== 'QM') throw error;\n      console.warn('[NOVA QM] 하우스맨 DB 우선등록 실패 · 기존 모바일 요청으로 fallback', error);\n      const legacy = await callServer('createMobileHousemanRequest', state.token, Object.assign({}, payload || {}, {\n        requestSource: 'QM', createdFrom: 'MOBILE', assignmentMode: 'UNASSIGNED', handover: false\n      }));",
    "      if (!['QM', 'PUBLIC'].includes(role)) throw error; // PUBLIC_HOUSEMAN_REQUEST_V1\n      console.warn(`[NOVA ${role}] 하우스맨 DB 우선등록 실패 · 기존 모바일 요청으로 fallback`, error);\n      const legacy = await callServer('createMobileHousemanRequest', state.token, Object.assign({}, payload || {}, {\n        requestSource: role, createdFrom: 'MOBILE', assignmentMode: role === 'PUBLIC' ? 'AUTO' : 'UNASSIGNED',\n        realtimeAssignmentSnapshot: publicAssignment, handover: false\n      }));",
    'public realtime fallback'
)

client = replace_once(
    client,
    "    const mode = String(payload.assignmentMode || '').trim().toUpperCase();\n    if (mode === 'UNASSIGNED') return { building: `${String(payload.roomNo || '').charAt(0)}동`, employeeNo: '', employeeNos: [], names: [], currentShift: '', activeShiftCodes: [] };",
    "    const mode = String(payload.assignmentMode || '').trim().toUpperCase();\n    const supplied = payload.realtimeAssignmentSnapshot && typeof payload.realtimeAssignmentSnapshot === 'object'\n      ? payload.realtimeAssignmentSnapshot : null; // PUBLIC_HOUSEMAN_REQUEST_V1\n    if (mode === 'AUTO' && supplied && String(supplied.employeeNo || '').trim()) {\n      return {\n        building: String(supplied.building || `${String(payload.roomNo || '').charAt(0)}동`),\n        employeeNo: String(supplied.employeeNo || '').trim(),\n        name: String(supplied.name || ''),\n        employeeNos: Array.isArray(supplied.employeeNos) ? supplied.employeeNos.map(String).filter(Boolean) : [String(supplied.employeeNo || '').trim()].filter(Boolean),\n        names: Array.isArray(supplied.names) ? supplied.names.map(String) : [String(supplied.name || supplied.employeeNo || '')],\n        currentShift: String(supplied.currentShift || '').trim().toUpperCase(),\n        activeShiftCodes: Array.isArray(supplied.activeShiftCodes) ? supplied.activeShiftCodes.map(code => String(code || '').trim().toUpperCase()).filter(Boolean) : []\n      };\n    }\n    if (mode === 'UNASSIGNED') return { building: `${String(payload.roomNo || '').charAt(0)}동`, employeeNo: '', employeeNos: [], names: [], currentShift: '', activeShiftCodes: [] };",
    'supplied auto assignment snapshot'
)

client = replace_once(
    client,
    "      actions += `<button data-houseman-request=\"${escapeAttr(room.roomNo)}\">하우스맨 요청</button>`;\n    } else if (role === 'QM') {",
    "      actions += `<button data-houseman-request=\"${escapeAttr(room.roomNo)}\" data-houseman-request-menu=\"cleaning\">하우스맨 요청</button>`;\n    } else if (role === 'QM') {",
    'roommaid request menu marker'
)

client = replace_once(
    client,
    "      actions += `<button data-houseman-request=\"${escapeAttr(room.roomNo)}\">하우스맨 요청</button>`;\n    }\n    return `<article class=\"mobile-room-card",
    "      actions += `<button data-houseman-request=\"${escapeAttr(room.roomNo)}\" data-houseman-request-menu=\"qm\">하우스맨 요청</button>`;\n    } else if (role === 'PUBLIC') { // PUBLIC_HOUSEMAN_REQUEST_V1\n      actions += `<button data-houseman-request=\"${escapeAttr(room.roomNo)}\" data-houseman-request-menu=\"public\">하우스맨 요청</button>`;\n    }\n    return `<article class=\"mobile-room-card",
    'public request button'
)

client = replace_once(
    client,
    "  function openMobileHousemanRequest_(roomNo) { // (모바일 하우스맨 요청 등록창)\n    const parts = state.mobile.data?.codes?.orderParts || [];",
    "  function openMobileHousemanRequest_(roomNo) { // (모바일 하우스맨 요청 등록창) // PUBLIC_HOUSEMAN_REQUEST_V1\n    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();\n    const rawParts = state.mobile.data?.codes?.orderParts || [];\n    const parts = role === 'PUBLIC'\n      ? [{ label: '습득물' }, { label: '기타' }]\n      : rawParts;",
    'public part choices'
)

client = replace_once(
    client,
    "      if (!['ROOMMAID', 'QM'].includes(role)) { // QM_HOUSEMAN_REQUEST_PARITY_V1",
    "      if (!['ROOMMAID', 'QM', 'PUBLIC'].includes(role)) { // QM_HOUSEMAN_REQUEST_PARITY_V1 · PUBLIC_HOUSEMAN_REQUEST_V1",
    'submit public fast route'
)

client = replace_once(
    client,
    "        if (resume && resume.roomNo && savedAt && Date.now() - savedAt <= 5 * 60 * 1000) return 'cleaning';",
    "        if (resume && resume.roomNo && savedAt && Date.now() - savedAt <= 5 * 60 * 1000) return String(resume.menu || 'cleaning'); // PUBLIC_HOUSEMAN_REQUEST_V1",
    'photo resume active menu'
)

# ---------- 10_Mobile.js ----------
insert_anchor = "function createMobileHousemanRequest(token, payload) { // (룸메이드·QM 객실 하우스맨 요청)"
if insert_anchor not in mobile:
    raise SystemExit('mobile create anchor not found')
public_assignment_fn = """function getMobilePublicHousemanAutoAssignment(token, payload) { // (객실퍼블릭 습득물 요청 담당동 자동배정) // PUBLIC_HOUSEMAN_REQUEST_V1
  return measureResponse_('getMobilePublicHousemanAutoAssignment', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const user = auth.user;
    if (String(user.role || '').trim().toUpperCase() !== 'PUBLIC') throw new Error('객실퍼블릭 계정만 사용할 수 있습니다.');
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = resolveUserSessionSite_(user, safe.site);
    const roomNo = String(safe.roomNo || '').trim();
    if (!businessDate || !site || !roomNo) throw new Error('자동배정 확인에 업무일자·사업장·객실번호가 필요합니다.');
    const assignment = resolveHousemanAutoAssignee_(businessDate, site, roomNo);
    if (!assignment || !String(assignment.employeeNo || '').trim()) throw new Error('해당 동에 자동배정 가능한 하우스맨이 없습니다.');
    return { ok: true, businessDate, site, roomNo, assignment };
  });
}

"""
mobile = mobile.replace(insert_anchor, public_assignment_fn + "function createMobileHousemanRequest(token, payload) { // (룸메이드·QM·객실퍼블릭 객실 하우스맨 요청) // PUBLIC_HOUSEMAN_REQUEST_V1", 1)

mobile = replace_once(
    mobile,
    "    if (!['ROOMMAID', 'QM'].includes(role)) throw new Error('하우스맨 요청 권한이 없습니다.');\n\n    const safe = normalizeHousemanPayload_(payload);",
    "    if (!['ROOMMAID', 'QM', 'PUBLIC'].includes(role)) throw new Error('하우스맨 요청 권한이 없습니다.'); // PUBLIC_HOUSEMAN_REQUEST_V1\n\n    const rawPayload = payload || {};\n    const safe = normalizeHousemanPayload_(rawPayload);",
    'mobile request public role'
)

mobile = replace_once(
    mobile,
    "    if (!safe.part) throw new Error('파트를 선택하세요.');\n    if (!safe.items.length) throw new Error('요청 품목을 입력하세요.');",
    "    if (!safe.part) throw new Error('파트를 선택하세요.');\n    if (role === 'PUBLIC' && !['습득물', '기타'].includes(String(safe.part || '').trim())) throw new Error('객실퍼블릭 요청 파트는 습득물 또는 기타만 선택할 수 있습니다.'); // PUBLIC_HOUSEMAN_REQUEST_V1\n    if (!safe.items.length) throw new Error('요청 품목을 입력하세요.');",
    'public part server guard'
)

mobile = replace_once(
    mobile,
    "    const assignedNos = role === 'ROOMMAID'\n      ? [String(rowInfo.data['룸메이드사번'] || '').trim(), String(rowInfo.data['보조룸메이드사번'] || '').trim()].filter(Boolean)\n      : [String(rowInfo.data['QM사번'] || '').trim()].filter(Boolean);\n    if (!assignedNos.includes(user.employeeNo)) throw new Error('본인에게 배정된 객실에서만 요청할 수 있습니다.');\n\n    const writeLock = acquireWriteLock_();",
    "    const assignedNos = role === 'ROOMMAID'\n      ? [String(rowInfo.data['룸메이드사번'] || '').trim(), String(rowInfo.data['보조룸메이드사번'] || '').trim()].filter(Boolean)\n      : role === 'QM'\n        ? [String(rowInfo.data['QM사번'] || '').trim()].filter(Boolean)\n        : [];\n    if (role !== 'PUBLIC' && !assignedNos.includes(user.employeeNo)) throw new Error('본인에게 배정된 객실에서만 요청할 수 있습니다.');\n\n    let publicAssignment = null; // PUBLIC_HOUSEMAN_REQUEST_V1\n    if (role === 'PUBLIC') {\n      const supplied = rawPayload.realtimeAssignmentSnapshot && typeof rawPayload.realtimeAssignmentSnapshot === 'object'\n        ? rawPayload.realtimeAssignmentSnapshot : null;\n      publicAssignment = supplied && String(supplied.employeeNo || '').trim()\n        ? normalizeRealtimeHousemanAssignmentSnapshot_(safe.businessDate, safe.site, safe.roomNo, supplied)\n        : resolveHousemanAutoAssignee_(safe.businessDate, safe.site, safe.roomNo);\n      if (!publicAssignment || !String(publicAssignment.employeeNo || '').trim()) throw new Error('해당 동에 자동배정 가능한 하우스맨이 없습니다.');\n      safe.assignedEmployeeNo = String(publicAssignment.employeeNo || '').trim();\n    }\n\n    const writeLock = acquireWriteLock_();",
    'public assignment validation'
)

mobile = replace_once(
    mobile,
    "    const detail = {\n      items: safe.items,\n      requester: user.name,\n      requestSource: role,\n      createdFrom: 'MOBILE'\n    };",
    "    const detail = {\n      items: safe.items,\n      requester: user.name,\n      requestSource: role,\n      createdFrom: 'MOBILE',\n      assignmentMode: role === 'PUBLIC' ? 'AUTO' : 'UNASSIGNED', // PUBLIC_HOUSEMAN_REQUEST_V1\n      autoAssigned: Boolean(publicAssignment),\n      assignedBuilding: publicAssignment ? publicAssignment.building : normalizeRoomBuilding_('', safe.roomNo),\n      assignedShiftCode: publicAssignment ? publicAssignment.currentShift : '',\n      assignedShiftCodes: publicAssignment ? publicAssignment.activeShiftCodes : [],\n      routeCandidateEmployeeNos: publicAssignment ? publicAssignment.employeeNos : [],\n      routeCandidateNames: publicAssignment ? publicAssignment.names : [],\n      routeLocked: !publicAssignment\n    };",
    'public assignment detail'
)

mobile = replace_once(
    mobile,
    "      '대상사번': '',\n      '처리상태': 'REGISTERED',",
    "      '대상사번': role === 'PUBLIC' ? safe.assignedEmployeeNo : '',\n      '처리상태': role === 'PUBLIC' && safe.assignedEmployeeNo ? 'ASSIGNED' : 'REGISTERED', // PUBLIC_HOUSEMAN_REQUEST_V1",
    'public order status'
)
mobile = replace_once(
    mobile,
    "      '배정사번': '',\n      '중요여부': safe.important ? 'Y' : 'N',",
    "      '배정사번': role === 'PUBLIC' ? safe.assignedEmployeeNo : '', // PUBLIC_HOUSEMAN_REQUEST_V1\n      '중요여부': safe.important ? 'Y' : 'N',",
    'public assigned employee'
)
mobile = replace_once(
    mobile,
    "    appendHousemanAudit_(order, 'CREATED_MOBILE', user.employeeNo, version, { role });",
    "    appendHousemanAudit_(order, 'CREATED_MOBILE', user.employeeNo, version, { role, autoAssignment: publicAssignment || null }); // PUBLIC_HOUSEMAN_REQUEST_V1",
    'public audit assignment'
)

# ---------- HousemanRequestPhoto.js ----------
photo_server = photo_server.replace("['ROOMMAID', 'QM'].includes(role)", "['ROOMMAID', 'QM', 'PUBLIC'].includes(role)")
photo_server = photo_server.replace("!['ROOMMAID', 'QM'].includes(role)", "!['ROOMMAID', 'QM', 'PUBLIC'].includes(role)")
photo_server = photo_server.replace("|| !['ROOMMAID', 'QM'].includes(role)", "|| !['ROOMMAID', 'QM', 'PUBLIC'].includes(role)")
if MARKER not in photo_server:
    photo_server = photo_server.replace("/**\n * 룸메이드 하우스맨 요청 사진", "/**\n * 룸메이드·QM·객실퍼블릭 하우스맨 요청 사진 // PUBLIC_HOUSEMAN_REQUEST_V1", 1)

# ---------- HousemanRequestPhotoClient.html ----------
photo_client = replace_once(
    photo_client,
    "  let activeRoomNo = '';\n  let photoSelectionActive = false;",
    "  let activeRoomNo = '';\n  let activeRequestMenu = 'cleaning'; // PUBLIC_HOUSEMAN_REQUEST_V1\n  let photoSelectionActive = false;",
    'photo active request menu'
)
photo_client = replace_once(
    photo_client,
    "      activeRoomNo = String(requestButton.dataset.housemanRequest || '').trim();\n      resetHousemanPhotoSelection_();",
    "      activeRoomNo = String(requestButton.dataset.housemanRequest || '').trim();\n      activeRequestMenu = String(requestButton.dataset.housemanRequestMenu || 'cleaning').trim() || 'cleaning'; // PUBLIC_HOUSEMAN_REQUEST_V1\n      resetHousemanPhotoSelection_();",
    'photo request menu capture'
)
photo_client = replace_once(
    photo_client,
    "      roomNo: activeRoomNo,\n      part: String(document.getElementById('mobileRequestPart')?.value || ''),",
    "      roomNo: activeRoomNo,\n      menu: activeRequestMenu, // PUBLIC_HOUSEMAN_REQUEST_V1\n      part: String(document.getElementById('mobileRequestPart')?.value || ''),",
    'photo resume menu save'
)
photo_client = replace_once(
    photo_client,
    "      sessionStorage.setItem('novaActiveMenu', 'cleaning');",
    "      sessionStorage.setItem('novaActiveMenu', activeRequestMenu || 'cleaning'); // PUBLIC_HOUSEMAN_REQUEST_V1",
    'photo persist session menu'
)
photo_client = replace_once(
    photo_client,
    "    try { sessionStorage.setItem('novaActiveMenu', 'cleaning'); } catch (ignore) {}",
    "    activeRequestMenu = String(context.menu || 'cleaning').trim() || 'cleaning'; // PUBLIC_HOUSEMAN_REQUEST_V1\n    try { sessionStorage.setItem('novaActiveMenu', activeRequestMenu); } catch (ignore) {}",
    'photo restore session menu'
)

# Safety checks
for required in [
    'PUBLIC_HOUSEMAN_REQUEST_V1',
    "['ROOMMAID', 'QM', 'PUBLIC'].includes(role)",
    "data-houseman-request-menu=\"public\"",
    "getMobilePublicHousemanAutoAssignment",
    "role === 'PUBLIC' ? 'AUTO' : 'UNASSIGNED'",
    "[{ label: '습득물' }, { label: '기타' }]",
]:
    if required not in client:
        raise SystemExit('Client safety marker missing: ' + required)
for required in [
    'PUBLIC_HOUSEMAN_REQUEST_V1',
    'getMobilePublicHousemanAutoAssignment',
    "['습득물', '기타']",
    "'처리상태': role === 'PUBLIC' && safe.assignedEmployeeNo ? 'ASSIGNED' : 'REGISTERED'",
]:
    if required not in mobile:
        raise SystemExit('Mobile safety marker missing: ' + required)
for required in ["'PUBLIC'", 'requestSource !== role']:
    if required not in photo_server:
        raise SystemExit('Photo server safety marker missing: ' + required)
for required in ['PUBLIC_HOUSEMAN_REQUEST_V1', 'activeRequestMenu', 'context.menu']:
    if required not in photo_client:
        raise SystemExit('Photo client safety marker missing: ' + required)

client_path.write_text(client, encoding='utf-8')
mobile_path.write_text(mobile, encoding='utf-8')
photo_server_path.write_text(photo_server, encoding='utf-8')
photo_client_path.write_text(photo_client, encoding='utf-8')
print('Applied PUBLIC_HOUSEMAN_REQUEST_V1')
