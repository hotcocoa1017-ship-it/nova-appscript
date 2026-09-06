from pathlib import Path

MARKER = 'SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1'

config_path = Path('00_Config.js')
bridge_path = Path('RealtimeBridge.js')
client_path = Path('Client.html')
index_path = Path('Index.html')

config = config_path.read_text(encoding='utf-8')
bridge = bridge_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')
index = index_path.read_text(encoding='utf-8')


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)

# 1) 공통 업무일자: 09:00 이전은 전일, 09:00부터 당일.
if 'NOVA_BUSINESS_DATE_0900_V1' not in config:
    old = """function businessDateText_() { // (기본 업무일자 문자열)\n  return Utilities.formatDate(new Date(), NOVA.TIMEZONE, NOVA.DATE_FORMAT);\n}"""
    new = """function businessDateText_() { // (공통 업무일자 · 09:00 이전 전일 · NOVA_BUSINESS_DATE_0900_V1)\n  const now = new Date();\n  const localHour = Number(Utilities.formatDate(now, NOVA.TIMEZONE, 'H'));\n  const businessAt = localHour < 9 ? new Date(now.getTime() - 24 * 60 * 60 * 1000) : now;\n  return Utilities.formatDate(businessAt, NOVA.TIMEZONE, NOVA.DATE_FORMAT);\n}"""
    config = replace_once(config, old, new, 'businessDateText_')

# 2) 서버 설정에 근무조/담당동 DB-first kill switch 추가.
if 'NOVA_SHIFT_ZONE_DB_FIRST_ENABLED' not in bridge:
    bridge = replace_once(
        bridge,
        "  let qmDraftDbFirstEnabled = false;\n",
        "  let qmDraftDbFirstEnabled = false;\n  const shiftZoneDbFirstEnabled = String(props.getProperty('NOVA_SHIFT_ZONE_DB_FIRST_ENABLED') || 'Y').trim().toUpperCase() !== 'N'; // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1\n",
        'RealtimeBridge flag declaration'
    )
    bridge = replace_once(
        bridge,
        "    qmDraftDbFirstEnabled // QM_DRAFT_DB_FIRST_V1\n",
        "    qmDraftDbFirstEnabled, // QM_DRAFT_DB_FIRST_V1\n    shiftZoneDbFirstEnabled // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1\n",
        'RealtimeBridge flag response'
    )
    bridge = replace_once(
        bridge,
        "  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES')) {\n    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', '');\n  }\n",
        "  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES')) {\n    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', '');\n  }\n  if (!props.getProperty('NOVA_SHIFT_ZONE_DB_FIRST_ENABLED')) {\n    props.setProperty('NOVA_SHIFT_ZONE_DB_FIRST_ENABLED', 'Y');\n  }\n",
        'RealtimeBridge setup flag'
    )

# 3) Client Realtime 상태에 전환 플래그 추가.
if 'shiftZoneDbFirstEnabled: false' not in client:
    client = replace_once(
        client,
        "    qmDraftDbFirstEnabled: false,\n",
        "    qmDraftDbFirstEnabled: false,\n    shiftZoneDbFirstEnabled: false, // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1\n",
        'Client realtime state flag'
    )
    client = replace_once(
        client,
        "        novaRealtime_.qmDraftDbFirstEnabled = Boolean(config?.qmDraftDbFirstEnabled); // QM_DRAFT_DB_FIRST_V1\n",
        "        novaRealtime_.qmDraftDbFirstEnabled = Boolean(config?.qmDraftDbFirstEnabled); // QM_DRAFT_DB_FIRST_V1\n        novaRealtime_.shiftZoneDbFirstEnabled = Boolean(config?.shiftZoneDbFirstEnabled); // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1\n",
        'Client realtime config flag'
    )

# 4) PostgreSQL RPC helper + 최초 1회 Sheet -> DB seed + 이후 DB source-of-truth.
if 'async function novaShiftZoneDbFirstLoad_' not in client:
    helper = r'''  async function novaShiftZoneDbRpc_(rpcName, payload) { // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1
    if (!novaRealtimeIsEnabled_()) throw new Error('Realtime DB 연결이 준비되지 않았습니다.');
    const auth = await novaRealtimeGetAuth_();
    const endpoint = `${String(auth.supabaseUrl || '').replace(/\/+$/, '')}/rest/v1/rpc/${rpcName}`;
    const send = async () => {
      const response = await novaRealtimeBoundedFetch_(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': String(auth.publishableKey || ''),
          'Authorization': `Bearer ${auth.token}`
        },
        body: JSON.stringify(payload || {})
      }, 6500);
      let data = null;
      try { data = await response.json(); } catch (_) {}
      return { response, data };
    };
    let { response, data } = await send();
    if (response.status === 401 && String(data?.code || '').trim().toUpperCase() === 'PGRST303') {
      await novaRealtimeSleep_(1200);
      ({ response, data } = await send());
    }
    if (!response.ok || !data?.ok) {
      const error = new Error(data?.message || data?.details || `근무조 DB 처리 오류 (${response.status})`);
      error.status = response.status;
      error.code = data?.code || '';
      throw error;
    }
    return data;
  }

  function novaShiftZoneMirrorLater_(serverFunction, payload) {
    window.setTimeout(() => {
      callServer(serverFunction, state.token, payload).catch(error => {
        console.warn(`[NOVA DB mirror] ${serverFunction} 실패`, error);
      });
    }, 0);
  }

  async function novaShiftZoneSeedFromLegacy_(legacy, payload, dbSnapshot) {
    const businessDate = String(payload?.businessDate || legacy?.businessDate || '').trim();
    const site = String(payload?.site || legacy?.site || '').trim();
    const assignments = legacy?.assignments || { A: [], B: [], C: [] };
    await novaShiftZoneDbRpc_('nova_houseman_shift_save_v2', {
      p_business_date: businessDate,
      p_site: site,
      p_assignments: assignments,
      p_request_id: novaRealtimeRequestId_('SHIFT_SEED', site)
    });

    const zones = legacy?.zoneAssignments || {};
    for (const [employeeNo, zone] of Object.entries(zones)) {
      const buildings = Array.isArray(zone?.buildings) ? zone.buildings.filter(Boolean) : [];
      if (!employeeNo || !buildings.length) continue;
      const action = dbSnapshot?.zoneAssignments?.[employeeNo] ? 'UPDATE' : 'SAVE';
      await novaShiftZoneDbRpc_('nova_houseman_zone_save_v1', {
        p_business_date: businessDate,
        p_site: site,
        p_employee_no: employeeNo,
        p_buildings: buildings,
        p_action: action,
        p_request_id: novaRealtimeRequestId_(`ZONE_SEED_${action}`, employeeNo)
      });
    }
  }

  async function novaShiftZoneDbFirstLoad_(payload) {
    if (!novaRealtime_.shiftZoneDbFirstEnabled || !novaRealtimeIsEnabled_()) {
      return callServer('getShiftManagementData', state.token, payload);
    }
    try {
      let result = await novaShiftZoneDbRpc_('nova_houseman_shift_zone_get_v2', {
        p_business_date: String(payload?.businessDate || ''),
        p_site: String(payload?.site || '')
      });
      if (result.initialized) return result;

      // 전환 직후에만 기존 Sheet 값을 1회 읽어 PostgreSQL을 초기화합니다.
      const legacy = await callServer('getShiftManagementData', state.token, payload);
      if (!legacy?.ok) throw new Error(legacy?.message || '기존 근무조 정보를 읽지 못했습니다.');
      await novaShiftZoneSeedFromLegacy_(legacy, payload, result);
      result = await novaShiftZoneDbRpc_('nova_houseman_shift_zone_get_v2', {
        p_business_date: String(payload?.businessDate || legacy.businessDate || ''),
        p_site: String(payload?.site || legacy.site || '')
      });
      return result;
    } catch (error) {
      console.warn('[NOVA SHIFT DB-first] 조회 실패 · 기존 조회를 임시 사용합니다.', error);
      return callServer('getShiftManagementData', state.token, payload);
    }
  }

  async function novaShiftAssignmentsDbFirstSave_(payload) {
    if (!novaRealtime_.shiftZoneDbFirstEnabled || !novaRealtimeIsEnabled_()) {
      return callServer('saveShiftAssignments', state.token, payload);
    }
    const result = await novaShiftZoneDbRpc_('nova_houseman_shift_save_v2', {
      p_business_date: String(payload?.businessDate || ''),
      p_site: String(payload?.site || ''),
      p_assignments: payload?.assignments || { A: [], B: [], C: [] },
      p_request_id: novaRealtimeRequestId_('SHIFT_SAVE', payload?.site || '')
    });
    // 사용자 응답은 DB 확정으로 끝내고 Sheet는 후행 미러로만 갱신합니다.
    novaShiftZoneMirrorLater_('saveShiftAssignments', payload);
    return result;
  }

  async function novaHousemanZoneDbFirstSave_(payload) {
    if (!novaRealtime_.shiftZoneDbFirstEnabled || !novaRealtimeIsEnabled_()) {
      return callServer('saveHousemanZoneAssignment', state.token, payload);
    }
    const result = await novaShiftZoneDbRpc_('nova_houseman_zone_save_v1', {
      p_business_date: String(payload?.businessDate || ''),
      p_site: String(payload?.site || ''),
      p_employee_no: String(payload?.employeeNo || ''),
      p_buildings: Array.isArray(payload?.buildings) ? payload.buildings : [],
      p_action: String(payload?.action || 'SAVE'),
      p_request_id: novaRealtimeRequestId_(`ZONE_${String(payload?.action || 'SAVE').toUpperCase()}`, payload?.employeeNo || '')
    });
    novaShiftZoneMirrorLater_('saveHousemanZoneAssignment', payload);
    return result;
  }

'''
    anchor = '  async function novaRealtimeCreateHousemanOrder_('
    if anchor not in client:
        raise SystemExit('Client DB helper insertion anchor not found')
    client = client.replace(anchor, helper + anchor, 1)

# 5) 기존 근무조/담당동 호출을 DB-first helper로 전환.
load_old = "const result = await callServer('getShiftManagementData', state.token, {"
load_new = "const result = await novaShiftZoneDbFirstLoad_({ // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1"
if load_old in client:
    client = client.replace(load_old, load_new, 1)

shift_old = "const result = await callServer('saveShiftAssignments', state.token, {"
shift_new = "const result = await novaShiftAssignmentsDbFirstSave_({ // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1"
if shift_old in client:
    client = client.replace(shift_old, shift_new, 1)

zone_old = "const result = await callServer('saveHousemanZoneAssignment', state.token, {"
zone_new = "const result = await novaHousemanZoneDbFirstSave_({ // SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1"
if zone_old in client:
    client = client.replace(zone_old, zone_new, 1)

# 6) 하우스맨 카드: 객실/상태/시간 위계 강화. 기능/버튼 흐름은 그대로 유지.
if 'houseman-card-v2' not in client:
    old_article = """    return `<article class=\"mobile-task-card ${order.important ? 'important' : ''}\" data-mobile-order-id=\"${escapeAttr(order.orderId)}\">\n      <div class=\"mobile-card-top\"><strong>${escapeHtml(order.roomNo || '공용')}</strong><span class=\"status-chip status-${escapeAttr(order.statusCode)}\">${escapeHtml(order.statusLabel)}</span></div>\n      <div class=\"mobile-task-title\">${escapeHtml(order.itemSummary || '-')}</div>\n      <div class=\"mobile-task-meta\"><span>${escapeHtml(order.part || '-')}</span><span>${escapeHtml(assigneeDisplay)}</span></div>"""
    new_article = """    const registeredAtText = String(order.registeredAt || '').trim();\n    const updatedAtText = String(order.updatedAt || '').trim();\n    return `<article class=\"mobile-task-card houseman-card-v2 ${order.important ? 'important' : ''} ${mine ? 'mine' : 'shared'}\" data-houseman-status=\"${escapeAttr(order.statusCode || '')}\" data-mobile-order-id=\"${escapeAttr(order.orderId)}\">\n      <div class=\"mobile-card-top\"><strong>${escapeHtml(order.roomNo || '공용')}</strong><span class=\"status-chip status-${escapeAttr(order.statusCode)}\">${escapeHtml(order.statusLabel)}</span></div>\n      <div class=\"mobile-task-title\">${escapeHtml(order.itemSummary || '-')}</div>\n      <div class=\"mobile-task-meta\"><span>${escapeHtml(order.part || '-')}</span><span>${escapeHtml(assigneeDisplay)}</span></div>\n      <div class=\"houseman-card-time\"><span>등록 ${escapeHtml(registeredAtText.slice(5, 16) || '-')}</span>${updatedAtText && updatedAtText !== registeredAtText ? `<span>변경 ${escapeHtml(updatedAtText.slice(5, 16))}</span>` : ''}</div>"""
    client = replace_once(client, old_article, new_article, 'Houseman mobile card')

# 7) UI 스타일 include를 하우스맨 패치 뒤에만 추가.
if "include_('HousemanUiV2')" not in index:
    index = replace_once(
        index,
        "  <?!= include_('HousemanUiPerformancePatch'); ?>\n",
        "  <?!= include_('HousemanUiPerformancePatch'); ?>\n  <?!= include_('HousemanUiV2'); ?> <!-- HOUSEMAN_MOBILE_UI_V2 -->\n",
        'Index HousemanUiV2 include'
    )

# Safety gates
required = {
    '00_Config.js': ['NOVA_BUSINESS_DATE_0900_V1'],
    'RealtimeBridge.js': ['NOVA_SHIFT_ZONE_DB_FIRST_ENABLED', 'shiftZoneDbFirstEnabled'],
    'Client.html': [
        'SHIFT_ZONE_DBFIRST_HOUSEMAN_UI_V1',
        'nova_houseman_shift_zone_get_v2',
        'nova_houseman_shift_save_v2',
        'nova_houseman_zone_save_v1',
        'novaShiftZoneDbFirstLoad_',
        'novaShiftAssignmentsDbFirstSave_',
        'novaHousemanZoneDbFirstSave_',
        'houseman-card-v2',
        "callServer('saveShiftAssignments'",
        "callServer('saveHousemanZoneAssignment'"
    ],
    'Index.html': ["include_('HousemanUiV2')"]
}
for label, values in required.items():
    text = {'00_Config.js': config, 'RealtimeBridge.js': bridge, 'Client.html': client, 'Index.html': index}[label]
    missing = [value for value in values if value not in text]
    if missing:
        raise SystemExit(f'{label} validation failed: {missing}')

# The interactive management path must no longer call legacy directly.
if load_old in client or shift_old in client or zone_old in client:
    raise SystemExit('Legacy shift/zone primary call remains in Client.html')

config_path.write_text(config, encoding='utf-8')
bridge_path.write_text(bridge, encoding='utf-8')
client_path.write_text(client, encoding='utf-8')
index_path.write_text(index, encoding='utf-8')
print(f'Applied {MARKER}: 09:00 business date + shift/zone DB-first + Houseman mobile UI v2.')
