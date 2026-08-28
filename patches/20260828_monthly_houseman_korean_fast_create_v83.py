from pathlib import Path

client_path = Path('Client.html')
monthly_path = Path('11_Monthly.js')
client = client_path.read_text(encoding='utf-8')
monthly = monthly_path.read_text(encoding='utf-8')

# 1) Lightweight server-side assignment resolver for monthly page.
server_marker = """function getMonthlyHousemanOrderOptions(token) { // (월별조회 하우스맨 등록창 코드옵션 직접 조회)\n"""
if server_marker not in monthly:
    raise SystemExit('V83_SERVER_MARKER_NOT_FOUND')
server_insert = r"""
function getMonthlyHousemanAutoAssignment(token, payload) { // (월별조회 자동배정 후보 사전확정)
  return measureResponse_('getMonthlyHousemanAutoAssignment', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const businessDate = normalizeBusinessDate_(safe.businessDate);
    const site = String(safe.site || '').trim();
    const roomNo = String(safe.roomNo || '').trim();
    if (!businessDate || !site || !roomNo) {
      throw new Error('자동배정 확인에 필요한 업무일자·사업장·객실번호가 없습니다.');
    }
    const assignment = resolveHousemanAutoAssignee_(businessDate, site, roomNo);
    return {
      ok: true,
      businessDate,
      site,
      roomNo,
      assignment
    };
  });
}

"""
monthly = monthly.replace(server_marker, server_insert + server_marker, 1)

# 2) Insert Korean 2-set composer + monthly realtime helpers before modal opener.
client_marker = """  async function openMonthlyHousemanOrderModal_() { // (일별 하우스맨 이력에서 오더 등록)\n"""
if client_marker not in client:
    raise SystemExit('V83_CLIENT_MODAL_MARKER_NOT_FOUND')
helpers = r"""
  const novaMonthlyHousemanAssignmentCache_ = new Map();
  let novaMonthlyHousemanAssignmentTimer_ = null;

  function novaMonthlyComposeHangulKeys_(rawText) { // (영문키를 두벌식 한글 음절로 조합)
    const raw = String(rawText || '');
    if (!raw) return '';
    const L = { r:0,R:1,s:2,e:3,E:4,f:5,a:6,q:7,Q:8,t:9,T:10,d:11,w:12,W:13,c:14,z:15,x:16,v:17,g:18 };
    const LJ = { r:'ㄱ',R:'ㄲ',s:'ㄴ',e:'ㄷ',E:'ㄸ',f:'ㄹ',a:'ㅁ',q:'ㅂ',Q:'ㅃ',t:'ㅅ',T:'ㅆ',d:'ㅇ',w:'ㅈ',W:'ㅉ',c:'ㅊ',z:'ㅋ',x:'ㅌ',v:'ㅍ',g:'ㅎ' };
    const V = { k:0,o:1,i:2,O:3,j:4,p:5,u:6,P:7,h:8,hk:9,ho:10,hl:11,y:12,n:13,nj:14,np:15,nl:16,b:17,m:18,ml:19,l:20 };
    const VJ = { k:'ㅏ',o:'ㅐ',i:'ㅑ',O:'ㅒ',j:'ㅓ',p:'ㅔ',u:'ㅕ',P:'ㅖ',h:'ㅗ',hk:'ㅘ',ho:'ㅙ',hl:'ㅚ',y:'ㅛ',n:'ㅜ',nj:'ㅝ',np:'ㅞ',nl:'ㅟ',b:'ㅠ',m:'ㅡ',ml:'ㅢ',l:'ㅣ' };
    const T = { r:1,R:2,rt:3,s:4,sw:5,sg:6,e:7,f:8,fr:9,fa:10,fq:11,ft:12,fx:13,fv:14,fg:15,a:16,q:17,qt:18,t:19,T:20,d:21,w:22,c:23,z:24,x:25,v:26,g:27 };
    const V_COMBINE = { 'h|k':'hk','h|o':'ho','h|l':'hl','n|j':'nj','n|p':'np','n|l':'nl','m|l':'ml' };
    const T_COMBINE = { 'r|t':'rt','s|w':'sw','s|g':'sg','f|r':'fr','f|a':'fa','f|q':'fq','f|t':'ft','f|x':'fx','f|v':'fv','f|g':'fg','q|t':'qt' };
    const normalizeKey = key => {
      if (Object.prototype.hasOwnProperty.call(L, key) || Object.prototype.hasOwnProperty.call(V, key)) return key;
      const lower = String(key || '').toLowerCase();
      return Object.prototype.hasOwnProperty.call(L, lower) || Object.prototype.hasOwnProperty.call(V, lower) ? lower : key;
    };
    const chars = Array.from(raw, normalizeKey);
    let out = '';
    let l = '';
    let v = '';
    let t = '';
    const syllable = (lk, vk, tk = '') => {
      if (!lk && vk) return VJ[vk] || vk;
      if (lk && !vk) return LJ[lk] || lk;
      if (!Object.prototype.hasOwnProperty.call(L, lk) || !Object.prototype.hasOwnProperty.call(V, vk)) {
        return `${LJ[lk] || lk}${VJ[vk] || vk}${tk ? (LJ[tk] || tk) : ''}`;
      }
      const finalIndex = tk && Object.prototype.hasOwnProperty.call(T, tk) ? T[tk] : 0;
      return String.fromCharCode(0xAC00 + ((L[lk] * 21 + V[vk]) * 28) + finalIndex);
    };
    const flush = () => {
      if (l || v) out += syllable(l, v, t);
      l = ''; v = ''; t = '';
    };

    chars.forEach(key => {
      const vowel = Object.prototype.hasOwnProperty.call(V, key);
      const consonant = Object.prototype.hasOwnProperty.call(L, key);
      if (!vowel && !consonant) {
        flush();
        out += key;
        return;
      }

      if (vowel) {
        if (!l) {
          if (!v) { v = key; return; }
          const combined = V_COMBINE[`${v}|${key}`] || '';
          if (combined) { v = combined; return; }
          flush();
          v = key;
          return;
        }
        if (!v) { v = key; return; }
        if (t) {
          let remainFinal = '';
          let movedInitial = t;
          if (t.length === 2) {
            remainFinal = t.charAt(0);
            movedInitial = t.charAt(1);
          }
          out += syllable(l, v, remainFinal);
          l = Object.prototype.hasOwnProperty.call(L, movedInitial) ? movedInitial : '';
          v = key;
          t = '';
          return;
        }
        const combined = V_COMBINE[`${v}|${key}`] || '';
        if (combined) { v = combined; return; }
        flush();
        v = key;
        return;
      }

      if (!l) {
        if (v) flush();
        l = key;
        return;
      }
      if (!v) {
        flush();
        l = key;
        return;
      }
      if (!t) {
        if (Object.prototype.hasOwnProperty.call(T, key)) {
          t = key;
        } else {
          flush();
          l = key;
        }
        return;
      }
      const compound = T_COMBINE[`${t}|${key}`] || '';
      if (compound) {
        t = compound;
      } else {
        flush();
        l = key;
      }
    });
    flush();
    return out;
  }

  function bindMonthlyKoreanItemInput_(input) { // (품목 영문키 입력도 한글로 자동변환)
    if (!input || input.dataset.novaKoreanBound === 'Y') return;
    input.dataset.novaKoreanBound = 'Y';
    input.setAttribute('lang', 'ko');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocapitalize', 'none');
    input.spellcheck = false;

    let rawKeys = '';
    let segmentStart = 0;
    let segmentEnd = 0;
    let internalChange = false;
    const reset = () => { rawKeys = ''; segmentStart = 0; segmentEnd = 0; };
    const renderRaw = () => {
      const composed = novaMonthlyComposeHangulKeys_(rawKeys);
      internalChange = true;
      input.setRangeText(composed, segmentStart, segmentEnd, 'end');
      internalChange = false;
      segmentEnd = segmentStart + composed.length;
    };

    input.addEventListener('compositionstart', reset);
    input.addEventListener('input', () => { if (!internalChange) reset(); });
    input.addEventListener('mousedown', reset);
    input.addEventListener('blur', reset);
    input.addEventListener('keydown', event => {
      if (event.isComposing || event.key === 'Process' || event.ctrlKey || event.metaKey || event.altKey) return;
      const selectionStart = Number(input.selectionStart ?? input.value.length);
      const selectionEnd = Number(input.selectionEnd ?? selectionStart);
      if (/^[A-Za-z]$/.test(event.key)) {
        if (!rawKeys || selectionStart !== segmentEnd || selectionEnd !== segmentEnd) {
          rawKeys = '';
          segmentStart = selectionStart;
          segmentEnd = selectionEnd;
        }
        event.preventDefault();
        rawKeys += event.key;
        renderRaw();
        return;
      }
      if (event.key === 'Backspace' && rawKeys && selectionStart === segmentEnd && selectionEnd === segmentEnd) {
        event.preventDefault();
        rawKeys = rawKeys.slice(0, -1);
        renderRaw();
        if (!rawKeys) reset();
        return;
      }
      reset();
    });
    input.addEventListener('paste', event => {
      const text = String(event.clipboardData?.getData('text') || '');
      if (!text || !/^[A-Za-z]+$/.test(text)) return;
      event.preventDefault();
      reset();
      const start = Number(input.selectionStart ?? input.value.length);
      const end = Number(input.selectionEnd ?? start);
      const converted = novaMonthlyComposeHangulKeys_(text);
      input.setRangeText(converted, start, end, 'end');
    });
  }

  function monthlyHousemanAssignmentKey_(payload) {
    return [payload?.businessDate, payload?.site, payload?.roomNo].map(value => String(value || '').trim()).join('|');
  }

  async function resolveMonthlyHousemanAutoAssignment_(payload) { // (입력 중 자동배정 후보 선조회·캐시)
    const key = monthlyHousemanAssignmentKey_(payload);
    if (!payload?.businessDate || !payload?.site || !/^\d{4}$/.test(String(payload?.roomNo || '').trim())) {
      throw new Error('자동배정 확인을 위해 사업장과 4자리 객실번호를 확인하세요.');
    }
    if (novaMonthlyHousemanAssignmentCache_.has(key)) {
      return await novaMonthlyHousemanAssignmentCache_.get(key);
    }
    const promise = callServer('getMonthlyHousemanAutoAssignment', state.token, {
      businessDate: payload.businessDate,
      site: payload.site,
      roomNo: payload.roomNo
    }).then(result => {
      if (!result?.ok || !result.assignment?.employeeNo) {
        throw new Error('담당 하우스맨 자동배정 정보를 확인할 수 없습니다.');
      }
      return result.assignment;
    }).catch(error => {
      novaMonthlyHousemanAssignmentCache_.delete(key);
      throw error;
    });
    novaMonthlyHousemanAssignmentCache_.set(key, promise);
    return await promise;
  }

  function queueMonthlyHousemanAssignmentPreload_() { // (객실번호 입력 중 서버후보를 미리 준비)
    window.clearTimeout(novaMonthlyHousemanAssignmentTimer_);
    novaMonthlyHousemanAssignmentTimer_ = window.setTimeout(() => {
      const mode = String($('monthlyOrderAssignmentMode')?.value || '').toUpperCase();
      const payload = {
        businessDate: String($('monthlyOrderDate')?.value || '').trim(),
        site: String($('monthlyOrderSite')?.value || '').trim(),
        roomNo: String($('monthlyOrderRoomNo')?.value || '').trim()
      };
      if (mode !== 'AUTO' || !/^\d{4}$/.test(payload.roomNo) || !payload.site) return;
      void resolveMonthlyHousemanAutoAssignment_(payload).catch(error => {
        console.warn('월별조회 하우스맨 자동배정 사전조회:', error?.message || error);
      });
    }, 120);
  }

  async function novaMonthlyRealtimeCreateHousemanOrder_(payload, assignment) { // (월별조회 PostgreSQL 선등록)
    if (!novaRealtimeIsEnabled_()) throw new Error('Realtime이 비활성화되어 있습니다.');
    const orderId = novaRealtimeHousemanOrderId_(payload.businessDate);
    const requestId = novaRealtimeRequestId_('HOUSEMAN_CREATE', payload.roomNo);
    const currentShift = String(assignment?.currentShift || '').trim().toUpperCase();
    const apiPayload = Object.assign({}, payload, {
      orderId,
      requestId,
      assignment: assignment || {},
      handoverTargetShift: payload.handover ? novaRealtimeNextShift_(currentShift) : ''
    });
    const result = await novaRealtimeFetch_('/v1/houseman-orders', {
      method: 'POST',
      headers: { 'X-Request-Id': requestId },
      body: JSON.stringify(apiPayload)
    });
    const order = novaRealtimeMapHousemanOrder_(result.order) || result.order;
    if (!order?.orderId) throw new Error('Realtime 오더 저장 응답이 올바르지 않습니다.');
    return {
      order,
      orderId,
      requestId,
      assignment,
      timing: result.timing || {},
      mirrorPayload: Object.assign({}, payload, {
        realtimeOrderId: orderId,
        realtimeAssignmentSnapshot: assignment
      })
    };
  }

  function monthlyHousemanRealtimeItem_(order, payload) { // (DB확정 오더를 현재 이력표에 즉시 추가)
    const assignedEmployeeNo = String(order?.assignedEmployeeNo || '').trim();
    const assignedName = String(order?.assignedName || '').trim();
    const itemSummary = String(order?.itemSummary || (payload.items || []).map(item => item.quantity > 1 ? `${item.name}×${item.quantity}` : item.name).join(', '));
    const part = String(order?.part || payload.part || '');
    const note = String(order?.note || payload.note || '');
    return {
      rowNumber: 0,
      recordId: String(order?.orderId || ''),
      typeCode: 'HOUSEMAN',
      typeLabel: '하우스맨',
      businessDate: String(order?.businessDate || payload.businessDate || ''),
      site: String(order?.site || payload.site || ''),
      roomNo: String(order?.roomNo || payload.roomNo || ''),
      employeeNos: assignedEmployeeNo ? [assignedEmployeeNo] : [],
      employeeNo: assignedEmployeeNo,
      employeeName: assignedName || assignedEmployeeNo || '-',
      employeeDisplay: assignedEmployeeNo ? `${assignedName || assignedEmployeeNo} (${assignedEmployeeNo})` : '-',
      statusCode: String(order?.statusCode || (assignedEmployeeNo ? 'ASSIGNED' : 'REGISTERED')),
      statusLabel: String(order?.statusLabel || (assignedEmployeeNo ? '배정' : '등록')),
      requestSource: 'MONTHLY_HISTORY',
      canDelete: false,
      detailText: [part, itemSummary, note].filter(Boolean).join(' · '),
      registeredAt: String(order?.registeredAt || ''),
      acceptedAt: '',
      startedAt: '',
      completedAt: '',
      eventAt: String(order?.registeredAt || ''),
      durationMinutes: null,
      cleaningType: '',
      cleaningTypeLabel: '',
      creditUnit: 0,
      part,
      itemSummary,
      requester: String(order?.requester || payload.requester || ''),
      photos: [],
      photoCount: 0,
      important: Boolean(order?.important ?? payload.important),
      handover: Boolean(order?.handover ?? payload.handover)
    };
  }

  function insertMonthlyHousemanRealtimeItem_(order, payload) { // (기존 리스트 유지·신규 1건만 즉시 추가)
    if (state.activeMenu !== 'monthly' || state.monthly.period !== 'DAILY' || String(state.monthly.type || '').toUpperCase() !== 'HOUSEMAN') return;
    if (Number(state.monthly.page || 1) !== 1 || !state.monthly.data) return;
    const item = monthlyHousemanRealtimeItem_(order, payload);
    if (String(state.monthly.date || '') && item.businessDate !== String(state.monthly.date || '')) return;
    if (String(state.monthly.site || '') && item.site !== String(state.monthly.site || '')) return;
    if (String(state.monthly.employeeNo || '') && !item.employeeNos.includes(String(state.monthly.employeeNo || ''))) return;
    const statusFilter = String(state.monthly.status || '').trim();
    if (statusFilter && statusFilter !== '전체' && ![item.statusCode, item.statusLabel, '진행중'].includes(statusFilter)) return;
    const search = String(state.monthly.search || '').trim().toLowerCase();
    if (search) {
      const text = [item.roomNo, item.site, item.employeeDisplay, item.detailText, item.requester].join(' ').toLowerCase();
      if (!text.includes(search)) return;
    }
    const currentItems = Array.isArray(state.monthly.data.items) ? state.monthly.data.items : [];
    state.monthly.data.items = [item, ...currentItems.filter(row => String(row.recordId || '') !== item.recordId)].slice(0, 100);
    if (state.monthly.data.pagination) {
      state.monthly.data.pagination = Object.assign({}, state.monthly.data.pagination, {
        total: Number(state.monthly.data.pagination.total || 0) + (currentItems.some(row => String(row.recordId || '') === item.recordId) ? 0 : 1)
      });
    }
    renderMonthlyTable_(state.monthly.data.items);
    renderMonthlyPagination_(state.monthly.data.pagination || { page: 1, pageCount: 1, total: state.monthly.data.items.length });
  }

  async function novaMonthlyRealtimeCancelHousemanOrder_(orderId) { // (DB등록취소 선확정)
    const requestId = novaRealtimeRequestId_('HOUSEMAN_CANCEL', orderId);
    return await novaRealtimeFetch_(`/v1/houseman-orders/${encodeURIComponent(orderId)}/cancel`, {
      method: 'POST',
      headers: { 'X-Request-Id': requestId },
      body: JSON.stringify({ requestId })
    });
  }

"""
client = client.replace(client_marker, helpers + client_marker, 1)

# 3) Make item input Korean-oriented and bind preloading.
old_item = """<label class=\"modal-field full\"><span>품목</span><input id=\"monthlyOrderItem\" list=\"monthlyHousemanItemSuggestions\" placeholder=\"품목을 선택하거나 입력하세요.\"></label>"""
new_item = """<label class=\"modal-field full\"><span>품목</span><input id=\"monthlyOrderItem\" lang=\"ko\" autocomplete=\"off\" autocapitalize=\"none\" list=\"monthlyHousemanItemSuggestions\" placeholder=\"품목을 한글로 입력하세요. (영문키도 한글 자동변환)\"></label>"""
if old_item not in client:
    raise SystemExit('V83_ITEM_INPUT_NOT_FOUND')
client = client.replace(old_item, new_item, 1)

old_bind = """    $('monthlyOrderRoomNo')?.focus();\n    $('monthlyOrderSubmit').addEventListener('click', submitMonthlyHousemanOrder_);\n"""
new_bind = """    const monthlyItemInput = $('monthlyOrderItem');
    bindMonthlyKoreanItemInput_(monthlyItemInput);
    $('monthlyOrderRoomNo')?.addEventListener('input', queueMonthlyHousemanAssignmentPreload_);
    $('monthlyOrderSite')?.addEventListener('change', queueMonthlyHousemanAssignmentPreload_);
    $('monthlyOrderAssignmentMode')?.addEventListener('change', queueMonthlyHousemanAssignmentPreload_);
    $('monthlyOrderRoomNo')?.focus();
    $('monthlyOrderSubmit').addEventListener('click', submitMonthlyHousemanOrder_);
"""
if old_bind not in client:
    raise SystemExit('V83_MODAL_BIND_NOT_FOUND')
client = client.replace(old_bind, new_bind, 1)

# 4) Replace monthly submit with DB-first fast path + background Sheet mirror.
start = client.find("  async function submitMonthlyHousemanOrder_() { // (월별조회 하우스맨 오더 등록)")
end = client.find("\n  function applyMonthlySubcategoryUi_", start)
if start < 0 or end < 0:
    raise SystemExit('V83_SUBMIT_FUNCTION_NOT_FOUND')
new_submit = r"""  async function submitMonthlyHousemanOrder_() { // (월별조회 하우스맨 오더 등록·DB 선확정)
    const button = $('monthlyOrderSubmit');
    if (!button) return;
    const payload = {
      businessDate: String($('monthlyOrderDate')?.value || state.monthly.date || '').trim(),
      site: String($('monthlyOrderSite')?.value || state.monthly.site || '').trim(),
      roomNo: String($('monthlyOrderRoomNo')?.value || '').trim(),
      part: String($('monthlyOrderPart')?.value || '').trim(),
      items: [{ name: String($('monthlyOrderItem')?.value || '').trim(), quantity: clampQuantity($('monthlyOrderQty')?.value) }],
      note: String($('monthlyOrderNote')?.value || '').trim(),
      requester: String($('monthlyOrderRequester')?.value || '오더테이커'),
      requestSource: 'MONTHLY_HISTORY',
      assignmentMode: String($('monthlyOrderAssignmentMode')?.value || 'AUTO'),
      important: Boolean($('monthlyOrderImportant')?.checked),
      handover: Boolean($('monthlyOrderHandover')?.checked)
    };
    if (!payload.businessDate) return showToast('업무일자를 선택하세요.');
    if (!payload.site) return showToast('사업장을 선택하세요.');
    if (!payload.roomNo) return showToast('객실번호를 입력하세요.');
    if (!payload.part) return showToast('파트를 선택하세요.');
    if (!payload.items[0].name) return showToast('품목을 입력하세요.');

    const original = button.textContent;
    const clickedAt = performance.now();
    button.disabled = true;
    button.textContent = '등록 중…';
    try {
      let realtimeFallbackReason = '';
      let assignment = null;
      if (String(payload.assignmentMode || '').toUpperCase() === 'AUTO') {
        assignment = await resolveMonthlyHousemanAutoAssignment_(payload);
      } else {
        assignment = {
          building: `${String(payload.roomNo || '').charAt(0)}동`,
          employeeNo: '', employeeNos: [], names: [], currentShift: '', activeShiftCodes: []
        };
      }

      if (!novaRealtime_.configLoaded) {
        const ready = await initNovaRealtime_();
        if (!ready && !novaRealtime_.configLoaded) realtimeFallbackReason = 'REALTIME_CONFIG_UNAVAILABLE';
      }

      if (novaRealtimeIsEnabled_()) {
        try {
          const realtime = await novaMonthlyRealtimeCreateHousemanOrder_(payload, assignment);
          const elapsed = Math.round(performance.now() - clickedAt);
          const dbMs = Math.max(0, Number(realtime.timing?.totalMs || 0));
          closeModal();
          insertMonthlyHousemanRealtimeItem_(realtime.order, payload);
          showToast(`${payload.roomNo}호 오더 등록 완료 · ${elapsed}ms`);
          setSyncStatus(`${payload.roomNo}호 DB 저장 ${dbMs}ms · 화면 ${elapsed}ms · 이력 동기화 중`);

          void mirrorRealtimeHousemanOrderToSheet_(realtime.mirrorPayload).then(mirrorResult => {
            if (!mirrorResult?.ok) return;
            if (state.activeMenu === 'monthly'
                && state.monthly.period === 'DAILY'
                && String(state.monthly.type || '').toUpperCase() === 'HOUSEMAN') {
              void loadMonthlyHistory({ page: Number(state.monthly.page || 1), preserveTable: true });
            }
          });
          return;
        } catch (realtimeError) {
          realtimeFallbackReason = String(realtimeError?.code || realtimeError?.message || 'REALTIME_ERROR')
            .replace(/\s+/g, ' ').trim().slice(0, 80);
          console.warn('[NOVA Realtime] 월별조회 하우스맨 등록은 기존 저장경로로 전환합니다.', realtimeError);
        }
      } else if (!realtimeFallbackReason) {
        realtimeFallbackReason = novaRealtime_.configLoaded ? 'REALTIME_DISABLED' : 'REALTIME_CONFIG_UNAVAILABLE';
      }

      const result = await callServer('createHousemanOrder', state.token, payload);
      if (!result?.ok) throw new Error(result?.message || '오더 등록에 실패했습니다.');
      const elapsed = Math.round(performance.now() - clickedAt);
      closeModal();
      showToast(`${payload.roomNo}호 오더 등록 완료 · ${elapsed}ms`);
      setSyncStatus(`${payload.roomNo}호 기존 저장경로 ${elapsed}ms · ${realtimeFallbackReason || 'LEGACY'}`);
      await loadMonthlyHistory({ page: 1, preserveTable: true });
    } catch (error) {
      showToast(error?.message || '오더 등록 오류');
      button.disabled = false;
      button.textContent = original;
    }
  }
"""
client = client[:start] + new_submit + client[end:]

# 5) Replace cancel flow so DB-first orders are removed from PostgreSQL before Sheet soft delete.
cancel_start = client.find("  async function cancelMonthlyHousemanOrder_(button) { // (월별조회 직접등록 하우스맨 오더 등록취소)")
cancel_end = client.find("\n  async function openMonthlyHousemanPhotoViewer_", cancel_start)
if cancel_start < 0 or cancel_end < 0:
    raise SystemExit('V83_CANCEL_FUNCTION_NOT_FOUND')
new_cancel = r"""  async function cancelMonthlyHousemanOrder_(button) { // (월별조회 직접등록 오더 DB+Sheet 등록취소)
    const orderId = String(button?.dataset?.monthlyOrderCancel || '').trim();
    const item = (state.monthly.data?.items || []).find(row => String(row.recordId || '') === orderId);
    if (!item || !item.canDelete) return showToast('등록취소할 수 없는 오더입니다.');
    if (!window.confirm(`${item.roomNo || '-'}호 하우스맨 오더를 삭제할까요?\n\n접수·처리 시작 전 오더만 삭제할 수 있습니다.`)) return;

    const original = button.textContent;
    button.disabled = true;
    button.textContent = '취소 중…';
    try {
      if (!novaRealtime_.configLoaded) await initNovaRealtime_();
      if (novaRealtimeIsEnabled_()) {
        const realtimeCancel = await novaMonthlyRealtimeCancelHousemanOrder_(orderId);
        if (!realtimeCancel?.ok) throw new Error('Realtime 오더 등록취소에 실패했습니다.');
      } else if (!novaRealtime_.configLoaded) {
        throw new Error('고속 서버 연결을 확인하지 못했습니다. 잠시 후 다시 등록취소하세요.');
      }

      const result = await callServer('deleteMonthlyHousemanOrder', state.token, {
        orderId,
        rowNumber: Number(item.rowNumber || 0)
      });
      if (!result?.ok) throw new Error(result?.message || '오더를 삭제하지 못했습니다.');
      showToast(result.message || `${item.roomNo || ''}호 오더 등록취소 완료`);
      await loadMonthlyHistory({ page: Number(state.monthly.page || 1), preserveTable: true });
    } catch (error) {
      showToast(error?.message || '오더 등록취소 오류');
      button.disabled = false;
      button.textContent = original;
    }
  }
"""
client = client[:cancel_start] + new_cancel + client[cancel_end:]

client_path.write_text(client, encoding='utf-8')
monthly_path.write_text(monthly, encoding='utf-8')

# Self-validation.
client_check = client_path.read_text(encoding='utf-8')
monthly_check = monthly_path.read_text(encoding='utf-8')
required_client = [
    'novaMonthlyComposeHangulKeys_',
    'bindMonthlyKoreanItemInput_',
    '영문키도 한글 자동변환',
    'getMonthlyHousemanAutoAssignment',
    'novaMonthlyRealtimeCreateHousemanOrder_',
    'insertMonthlyHousemanRealtimeItem_',
    'void mirrorRealtimeHousemanOrderToSheet_',
    '/cancel`,',
    'DB 저장 ${dbMs}ms',
]
required_monthly = [
    'function getMonthlyHousemanAutoAssignment',
    'resolveHousemanAutoAssignee_(businessDate, site, roomNo)',
]
for token in required_client:
    if token not in client_check:
        raise SystemExit(f'V83_CLIENT_VALIDATION_MISSING:{token}')
for token in required_monthly:
    if token not in monthly_check:
        raise SystemExit(f'V83_MONTHLY_VALIDATION_MISSING:{token}')
if "await callServer('createHousemanOrder', state.token, payload);" not in client_check:
    raise SystemExit('V83_LEGACY_FALLBACK_MISSING')
print('MONTHLY_HOUSEMAN_KOREAN_FAST_CREATE_V83_OK')
