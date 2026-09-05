from pathlib import Path
import re

MARKER = 'MONTHLY_HOUSEMAN_MANAGEMENT_V1'


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: patch anchor not found')
    return text.replace(old, new, 1)


# 1) Houseman active order query: cancelled orders must never reappear in Sheet fallback/mobile lists.
path = '07_Houseman.js'
text = read(path)
old = """      .filter(\n        item =>\n          String(\n            item.data['삭제여부']\n            || 'N'\n          )\n            .toUpperCase()\n            !== 'Y'\n      )\n      .map("""
new = """      .filter(\n        item =>\n          String(\n            item.data['삭제여부']\n            || 'N'\n          )\n            .toUpperCase()\n            !== 'Y'\n      )\n      .filter(\n        item =>\n          String(item.data['처리상태'] || '').trim().toUpperCase() !== 'CANCELLED'\n      ) // MONTHLY_HOUSEMAN_MANAGEMENT_V1 · 취소 오더는 현장 활성목록에서 제외\n      .map("""
text = replace_once(text, old, new, '07 cancelled filter')
write(path, text)


# 2) Monthly server: management options, rich Houseman item payload, cancel and soft-delete management.
path = '11_Monthly.js'
text = read(path)

# Replace legacy monthly-registration-only delete with explicit CANCEL + general pre-start soft delete.
pattern = re.compile(r"function deleteMonthlyHousemanOrder\(token, payload\) \{.*?\n\}\n\n\nfunction getMonthlyHousemanAutoAssignment", re.S)
if not pattern.search(text):
    if 'function cancelMonthlyManagedHousemanOrder' not in text:
        raise SystemExit('11 delete/cancel function anchor not found')
else:
    replacement = r'''function cancelMonthlyManagedHousemanOrder(token, payload) { // (월별조회 하우스맨 오더취소 · 이력 보존)
  return measureResponse_('cancelMonthlyManagedHousemanOrder', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    if (!orderId) throw new Error('취소할 오더 번호가 없습니다.');

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const found = findHousemanOrderRow_(sheet, orderId, Number(safe.rowNumber || 0));
      if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');
      if (String(found.data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ORDER) {
        throw new Error('하우스맨 오더만 취소할 수 있습니다.');
      }
      if (String(found.data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') {
        throw new Error('이미 삭제된 오더입니다.');
      }

      const statusCode = String(found.data['처리상태'] || '').trim().toUpperCase();
      if (statusCode === 'CANCELLED') {
        return { ok: true, orderId, alreadyCancelled: true, message: '이미 취소된 오더입니다.' };
      }
      if (!['REGISTERED', 'ASSIGNED'].includes(statusCode)
          || String(found.data['접수일시'] || '').trim()
          || String(found.data['처리시작일시'] || '').trim()
          || String(found.data['완료일시'] || '').trim()) {
        throw new Error('접수 또는 처리가 시작된 오더는 취소할 수 없습니다.');
      }

      let detail = {};
      try { detail = JSON.parse(String(found.data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
      const version = reserveDataVersion_({ lockHeld: true });
      const now = nowText_();
      detail = Object.assign({}, detail, {
        cancelled: true,
        cancelledAt: now,
        cancelledBy: user.employeeNo,
        cancelSource: 'MONTHLY_HISTORY'
      });

      updateRowByHeaders_(sheet, found.rowNumber, {
        '처리상태': 'CANCELLED',
        '세부내용JSON': JSON.stringify(detail),
        '수정일시': now,
        '변경버전': version
      });

      const users = getUserIndex_().byEmployeeNo;
      const statusCodeMap = {};
      getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
      statusCodeMap.CANCELLED = '오더취소';
      const updatedData = Object.assign({}, found.data, {
        '처리상태': 'CANCELLED',
        '세부내용JSON': JSON.stringify(detail),
        '수정일시': now,
        '변경버전': version
      });
      const order = housemanOrderObject_(updatedData, found.rowNumber, users, statusCodeMap);
      const auditRow = buildHousemanAuditRow_(sheet, order, 'CANCELLED', user.employeeNo, version, {
        source: 'MONTHLY_HISTORY',
        reason: 'ORDER_CANCELLED_BY_MANAGER'
      });
      const auditRowNumber = sheet.getLastRow() + 1;
      ensureSheetRowCapacity_(sheet, auditRowNumber);
      sheet.getRange(auditRowNumber, 1, 1, auditRow.length).setValues([auditRow]);
      SpreadsheetApp.flush();

      publishDataVersion_(version, {
        domains: ['ORDER'],
        businessDate: String(found.data['업무일자'] || '').trim(),
        site: String(found.data['사업장'] || '').trim(),
        lockHeld: true
      });

      return {
        ok: true,
        orderId,
        version,
        order,
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 취소했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function deleteMonthlyHousemanOrder(token, payload) { // (월별조회 하우스맨 오더 소프트삭제 · 감사이력 유지)
  return measureResponse_('deleteMonthlyHousemanOrder', () => {
    const user = requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    if (!orderId) throw new Error('삭제할 오더 번호가 없습니다.');

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
      const found = findHousemanOrderRow_(sheet, orderId, Number(safe.rowNumber || 0));
      if (!found) throw new Error('하우스맨 오더를 찾을 수 없습니다.');
      if (String(found.data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') {
        return { ok: true, orderId, alreadyDeleted: true, message: '이미 삭제된 오더입니다.' };
      }
      if (String(found.data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ORDER) {
        throw new Error('하우스맨 오더만 삭제할 수 있습니다.');
      }

      const statusCode = String(found.data['처리상태'] || '').trim().toUpperCase();
      if (!['REGISTERED', 'ASSIGNED', 'CANCELLED'].includes(statusCode)) {
        throw new Error('접수 또는 처리가 시작된 오더는 삭제할 수 없습니다.');
      }
      if (String(found.data['접수일시'] || '').trim()
          || String(found.data['처리시작일시'] || '').trim()
          || String(found.data['완료일시'] || '').trim()) {
        throw new Error('접수 또는 처리가 시작된 오더는 삭제할 수 없습니다.');
      }

      const users = getUserIndex_().byEmployeeNo;
      const statusCodeMap = {};
      getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
      statusCodeMap.CANCELLED = '오더취소';
      const current = housemanOrderObject_(found.data, found.rowNumber, users, statusCodeMap);
      const version = reserveDataVersion_({ lockHeld: true });
      const now = nowText_();

      updateRowByHeaders_(sheet, found.rowNumber, {
        '삭제여부': 'Y',
        '수정일시': now,
        '변경버전': version
      });

      const auditRow = buildHousemanAuditRow_(sheet, current, 'DELETED', user.employeeNo, version, {
        source: 'MONTHLY_HISTORY',
        reason: 'ORDER_DELETED_BY_MANAGER',
        previousStatus: statusCode
      });
      const auditRowNumber = sheet.getLastRow() + 1;
      ensureSheetRowCapacity_(sheet, auditRowNumber);
      sheet.getRange(auditRowNumber, 1, 1, auditRow.length).setValues([auditRow]);
      SpreadsheetApp.flush();

      publishDataVersion_(version, {
        domains: ['ORDER'],
        businessDate: String(found.data['업무일자'] || '').trim(),
        site: String(found.data['사업장'] || '').trim(),
        lockHeld: true
      });

      return {
        ok: true,
        orderId,
        version,
        message: `${String(found.data['객실번호'] || '').trim()}호 오더를 삭제했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}


function getMonthlyHousemanAutoAssignment'''
    text = pattern.sub(replacement, text, count=1)

old = """    return {\n      ok: true,\n      orderParts,\n      orderItems,\n      sites: getMonthlyConfiguredSites_()\n    };"""
new = """    return {\n      ok: true,\n      orderParts,\n      orderItems,\n      housemen: getPublicStaffList_(['HOUSEMAN']), // MONTHLY_HOUSEMAN_MANAGEMENT_V1\n      sites: getMonthlyConfiguredSites_()\n    };"""
text = replace_once(text, old, new, '11 order options housemen')

old = """  if (request.type === 'HOUSEMAN') {\n    options.orderParts = getCodes_('하우스맨파트');\n    options.orderItems = getCodes_('하우스맨품목');\n  }"""
new = """  if (request.type === 'HOUSEMAN') {\n    options.orderParts = getCodes_('하우스맨파트');\n    options.orderItems = getCodes_('하우스맨품목');\n    options.housemen = getPublicStaffList_(['HOUSEMAN']); // MONTHLY_HOUSEMAN_MANAGEMENT_V1\n  }"""
text = replace_once(text, old, new, '11 bundle housemen')

old = """  const creditUnit = typeCode === 'CLEANING' && ['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(statusCode)\n    ? getRoommaidCleaningCreditUnit_(cleaningType)\n    : 0;\n\n  return {"""
new = """  const creditUnit = typeCode === 'CLEANING' && ['CLEANING_COMPLETE', 'ROOMMAID_COMPLETE'].includes(statusCode)\n    ? getRoommaidCleaningCreditUnit_(cleaningType)\n    : 0;\n  const housemanItems = typeCode === 'HOUSEMAN'\n    ? (Array.isArray(detail.items) && detail.items.length\n        ? detail.items.map(item => ({ name: String(item && item.name || '').trim(), quantity: Math.max(1, Number(item && item.quantity || 1)) })).filter(item => item.name)\n        : (String(data['품목'] || '').trim() ? [{ name: String(data['품목'] || '').trim(), quantity: Math.max(1, Number(data['수량'] || 1)) }] : []))\n    : [];\n  const housemanPreStart = typeCode === 'HOUSEMAN'\n    && ['REGISTERED', 'ASSIGNED'].includes(statusCode)\n    && !acceptedAt && !startedAt && !completedAt;\n  const canEdit = typeCode === 'HOUSEMAN' && ['REGISTERED', 'ASSIGNED', 'ACCEPTED'].includes(statusCode) && !startedAt && !completedAt;\n  const canAssign = housemanPreStart;\n  const canCancel = housemanPreStart;\n  const canDelete = typeCode === 'HOUSEMAN'\n    && (housemanPreStart || (statusCode === 'CANCELLED' && !acceptedAt && !startedAt && !completedAt));\n\n  return {"""
text = replace_once(text, old, new, '11 rich item prelude')

old = """    requestSource: String(detail.requestSource || '').trim(),\n    canDelete: typeCode === 'HOUSEMAN'\n      && String(detail.requestSource || '').trim().toUpperCase() === 'MONTHLY_HISTORY'\n      && ['REGISTERED', 'ASSIGNED'].includes(statusCode),\n    detailText:"""
new = """    requestSource: String(detail.requestSource || '').trim(),\n    version: Number(data['변경버전'] || 0), // MONTHLY_HOUSEMAN_MANAGEMENT_V1\n    assignedEmployeeNo,\n    assignedName: assignedEmployeeNo && users[assignedEmployeeNo] ? users[assignedEmployeeNo].name : (assignedEmployeeNo || ''),\n    items: housemanItems,\n    note: String(data['추가내용'] || '').trim(),\n    canManage: typeCode === 'HOUSEMAN',\n    canEdit,\n    canAssign,\n    canCancel,\n    canDelete,\n    detailText:"""
text = replace_once(text, old, new, '11 rich item fields')

old = """function monthlyStatusLabel_(typeCode, statusCode, orderStatusMap) { // (월별 상태 표시명)\n  if (typeCode === 'HOUSEMAN') return orderStatusMap[statusCode] || statusCode || '-';"""
new = """function monthlyStatusLabel_(typeCode, statusCode, orderStatusMap) { // (월별 상태 표시명)\n  if (typeCode === 'HOUSEMAN') {\n    if (statusCode === 'CANCELLED') return '오더취소'; // MONTHLY_HOUSEMAN_MANAGEMENT_V1\n    return orderStatusMap[statusCode] || statusCode || '-';\n  }"""
text = replace_once(text, old, new, '11 cancelled label')

old = """function buildMonthlyStaffSummary_(items, users) { // (직원별 처리건수·평균시간 집계)\n  const groups = {};\n  items.forEach(item => {\n    const employeeNo = String(item.employeeNo || '').trim();"""
new = """function buildMonthlyStaffSummary_(items, users) { // (직원별 처리건수·평균시간 집계)\n  const groups = {};\n  items.forEach(item => {\n    if (item.typeCode === 'HOUSEMAN' && item.statusCode === 'CANCELLED') return; // MONTHLY_HOUSEMAN_MANAGEMENT_V1\n    const employeeNo = String(item.employeeNo || '').trim();"""
text = replace_once(text, old, new, '11 cancelled staff summary')

old = """    active: Math.max(0, items.length - completed),"""
new = """    active: Math.max(0, items.filter(item => !monthlyItemCompleted_(item) && !(item.typeCode === 'HOUSEMAN' && item.statusCode === 'CANCELLED')).length), // MONTHLY_HOUSEMAN_MANAGEMENT_V1"""
text = replace_once(text, old, new, '11 cancelled active summary')

write(path, text)


# 3) Client: add Houseman list to option cache; replace row registration-cancel with unified manager button; add manager modal/actions.
path = 'Client.html'
text = read(path)

old = """    return {\n      sites: Array.isArray(options.sites) ? options.sites.slice() : [],\n      parts: Array.isArray(options.orderParts) ? options.orderParts.slice() : [],\n      items: Array.isArray(options.orderItems) ? options.orderItems.slice() : []\n    };"""
new = """    return {\n      sites: Array.isArray(options.sites) ? options.sites.slice() : [],\n      parts: Array.isArray(options.orderParts) ? options.orderParts.slice() : [],\n      items: Array.isArray(options.orderItems) ? options.orderItems.slice() : [],\n      housemen: Array.isArray(options.housemen) ? options.housemen.slice() : [] // MONTHLY_HOUSEMAN_MANAGEMENT_V1\n    };"""
text = replace_once(text, old, new, 'Client option snapshot')

old = """    const items = Array.isArray(fallback?.orderItems) && fallback.orderItems.length\n      ? fallback.orderItems.slice()\n      : current.items;\n    if (state.monthly.data) {\n      state.monthly.data.options = Object.assign({}, state.monthly.data.options || {}, {\n        sites,\n        orderParts: parts,\n        orderItems: items\n      });\n    }\n    return { sites, parts, items };"""
new = """    const items = Array.isArray(fallback?.orderItems) && fallback.orderItems.length\n      ? fallback.orderItems.slice()\n      : current.items;\n    const housemen = Array.isArray(fallback?.housemen) && fallback.housemen.length\n      ? fallback.housemen.slice()\n      : current.housemen;\n    if (state.monthly.data) {\n      state.monthly.data.options = Object.assign({}, state.monthly.data.options || {}, {\n        sites,\n        orderParts: parts,\n        orderItems: items,\n        housemen\n      });\n    }\n    return { sites, parts, items, housemen }; // MONTHLY_HOUSEMAN_MANAGEMENT_V1"""
text = replace_once(text, old, new, 'Client merge housemen')

old = """            <td><span class=\"monthly-status\">${escapeHtml(item.statusLabel || '-')}</span>${item.canDelete ? `<button class=\"monthly-order-cancel\" type=\"button\" data-monthly-order-cancel=\"${escapeAttr(item.recordId)}\">등록취소</button>` : ''}</td>"""
new = """            <td><span class=\"monthly-status\">${escapeHtml(item.statusLabel || '-')}</span>${item.canManage !== false ? `<button class=\"monthly-order-manage\" type=\"button\" data-monthly-order-manage=\"${escapeAttr(item.recordId)}\">관리</button>` : ''}</td>"""
text = replace_once(text, old, new, 'Client houseman manage button')

old = """    $('monthlyTableBody').querySelectorAll('[data-monthly-order-cancel]').forEach(button => {\n      button.addEventListener('click', () => cancelMonthlyHousemanOrder_(button));\n    });"""
new = """    $('monthlyTableBody').querySelectorAll('[data-monthly-order-manage]').forEach(button => {\n      button.addEventListener('click', () => openMonthlyHousemanManageModal_(button.dataset.monthlyOrderManage));\n    }); // MONTHLY_HOUSEMAN_MANAGEMENT_V1\n    $('monthlyTableBody').querySelectorAll('[data-monthly-order-cancel]').forEach(button => {\n      button.addEventListener('click', () => cancelMonthlyHousemanOrder_(button));\n    });"""
text = replace_once(text, old, new, 'Client manage event')

pattern = re.compile(r"  async function cancelMonthlyHousemanOrder_\(button\) \{.*?\n  \}\n\n  async function openMonthlyHousemanPhotoViewer_", re.S)
if not pattern.search(text):
    if 'function openMonthlyHousemanManageModal_' not in text:
        raise SystemExit('Client legacy cancel function anchor not found')
else:
    replacement = r'''  function monthlyHousemanManageItem_(orderId) { // MONTHLY_HOUSEMAN_MANAGEMENT_V1
    return (state.monthly.data?.items || []).find(row => String(row.recordId || '') === String(orderId || '')) || null;
  }

  function appendMonthlyHousemanManageItemRow_(item = {}) {
    const root = $('monthlyHousemanManageItems');
    if (!root) return;
    const name = String(item.name || '');
    const quantity = Math.max(1, Math.min(99, Number(item.quantity || 1)));
    root.insertAdjacentHTML('beforeend', `<div class="monthly-houseman-manage-item"><input data-monthly-manage-item-name list="monthlyHousemanManageItemSuggestions" value="${escapeAttr(name)}" placeholder="품목"><input data-monthly-manage-item-qty type="number" min="1" max="99" value="${quantity}"><button type="button" class="secondary-button" data-monthly-manage-item-remove>삭제</button></div>`);
    root.lastElementChild?.querySelector('[data-monthly-manage-item-remove]')?.addEventListener('click', event => {
      event.currentTarget.closest('.monthly-houseman-manage-item')?.remove();
      if (!root.querySelector('[data-monthly-manage-item-name]')) appendMonthlyHousemanManageItemRow_({ quantity: 1 });
    });
  }

  function collectMonthlyHousemanManageItems_() {
    return Array.from(document.querySelectorAll('#monthlyHousemanManageItems .monthly-houseman-manage-item')).map(row => ({
      name: String(row.querySelector('[data-monthly-manage-item-name]')?.value || '').trim(),
      quantity: clampQuantity(row.querySelector('[data-monthly-manage-item-qty]')?.value || 1)
    })).filter(item => item.name);
  }

  async function openMonthlyHousemanManageModal_(orderId) { // (월별조회 하우스맨 오더 직접 관리)
    const item = monthlyHousemanManageItem_(orderId);
    if (!item || item.typeCode !== 'HOUSEMAN') return showToast('관리할 하우스맨 오더를 찾을 수 없습니다.');
    const options = state.monthly.data?.options || {};
    const parts = Array.isArray(options.orderParts) ? options.orderParts : [];
    const itemSuggestions = Array.isArray(options.orderItems) ? options.orderItems : [];
    const housemen = Array.isArray(options.housemen) ? options.housemen.slice() : [];
    if (item.assignedEmployeeNo && !housemen.some(user => String(user.employeeNo || '') === String(item.assignedEmployeeNo))) {
      housemen.unshift({ employeeNo: item.assignedEmployeeNo, name: item.assignedName || item.assignedEmployeeNo, job: '하우스맨' });
    }
    const currentItems = Array.isArray(item.items) && item.items.length ? item.items : [{ name: item.itemSummary || '', quantity: 1 }];
    const partOptions = parts.map(code => {
      const value = String(code?.label || code?.code || '').trim();
      return `<option value="${escapeAttr(value)}"${value === String(item.part || '') ? ' selected' : ''}>${escapeHtml(value)}</option>`;
    }).join('');
    const suggestionOptions = itemSuggestions.map(code => `<option value="${escapeAttr(code?.label || code?.code || '')}"></option>`).join('');
    const staffOptions = housemen.map(user => `<option value="${escapeAttr(user.employeeNo)}"${String(user.employeeNo) === String(item.assignedEmployeeNo || '') ? ' selected' : ''}>${escapeHtml(user.name || user.employeeNo)} (${escapeHtml(user.employeeNo)})</option>`).join('');
    openModal(`
      <div class="modal-card monthly-houseman-manage-modal">
        <div class="modal-header"><div><small>월별조회 · 하우스맨 관리</small><h2>${escapeHtml(item.roomNo || '-')}호 오더</h2><p>${escapeHtml(item.businessDate || '')} · ${escapeHtml(item.site || '')} · ${escapeHtml(item.statusLabel || '')}</p></div><button class="modal-close" type="button" data-close-modal>×</button></div>
        <div class="modal-body">
          <datalist id="monthlyHousemanManageItemSuggestions">${suggestionOptions}</datalist>
          <div class="modal-grid">
            <label class="modal-field"><span>파트</span><select id="monthlyManagePart"${item.canEdit ? '' : ' disabled'}>${partOptions}</select></label>
            <label class="modal-field"><span>요청자</span><input id="monthlyManageRequester" value="${escapeAttr(item.requester || '')}"${item.canEdit ? '' : ' disabled'}></label>
            <label class="modal-field full"><span>추가내용</span><textarea id="monthlyManageNote"${item.canEdit ? '' : ' disabled'}>${escapeHtml(item.note || '')}</textarea></label>
            <label class="modal-field full"><span>담당 하우스맨</span><select id="monthlyManageAssignee"${item.canAssign ? '' : ' disabled'}><option value="">직원 선택</option>${staffOptions}</select></label>
            <label class="modal-field"><span>중요</span><label class="toggle-compact"><input id="monthlyManageImportant" type="checkbox"${item.important ? ' checked' : ''}${item.canEdit ? '' : ' disabled'}> 중요 오더</label></label>
            <label class="modal-field"><span>인수인계</span><label class="toggle-compact"><input id="monthlyManageHandover" type="checkbox"${item.handover ? ' checked' : ''}${item.canEdit ? '' : ' disabled'}> 인수인계</label></label>
          </div>
          <div class="monthly-houseman-manage-heading"><strong>오더 품목</strong>${item.canEdit ? '<button id="monthlyManageAddItem" class="secondary-button" type="button">품목 추가</button>' : ''}</div>
          <div id="monthlyHousemanManageItems"></div>
          <div class="settings-help">수정·직원변경·취소는 접수/처리 전 단계에서만 가능합니다. 삭제는 실제 행을 제거하지 않고 감사이력을 남기는 안전한 소프트삭제입니다.</div>
          <div class="modal-actions monthly-houseman-manage-actions">
            ${item.canEdit ? '<button id="monthlyManageSave" class="action-button primary" type="button">내용 저장</button>' : ''}
            ${item.canAssign ? '<button id="monthlyManageAssign" class="action-button" type="button">직원 등록/변경</button>' : ''}
            ${item.canCancel ? '<button id="monthlyManageCancel" class="secondary-button danger" type="button">오더취소</button>' : ''}
            ${item.canDelete ? '<button id="monthlyManageDelete" class="secondary-button danger" type="button">삭제</button>' : ''}
          </div>
        </div>
      </div>`);
    currentItems.forEach(orderItem => appendMonthlyHousemanManageItemRow_(orderItem));
    if (!currentItems.length) appendMonthlyHousemanManageItemRow_({ quantity: 1 });
    if (!item.canEdit) document.querySelectorAll('#monthlyHousemanManageItems input, #monthlyHousemanManageItems button').forEach(element => { element.disabled = true; });
    $('monthlyManageAddItem')?.addEventListener('click', () => appendMonthlyHousemanManageItemRow_({ quantity: 1 }));
    $('monthlyManageSave')?.addEventListener('click', event => saveMonthlyHousemanManagedContent_(item, event.currentTarget));
    $('monthlyManageAssign')?.addEventListener('click', event => assignMonthlyHousemanManagedOrder_(item, event.currentTarget));
    $('monthlyManageCancel')?.addEventListener('click', event => cancelMonthlyHousemanManagedOrder_(item, event.currentTarget));
    $('monthlyManageDelete')?.addEventListener('click', event => deleteMonthlyHousemanManagedOrder_(item, event.currentTarget));
  }

  async function saveMonthlyHousemanManagedContent_(item, button) {
    const items = collectMonthlyHousemanManageItems_();
    if (!items.length) return showToast('품목을 1개 이상 입력하세요.');
    const part = String($('monthlyManagePart')?.value || '').trim();
    if (!part) return showToast('파트를 선택하세요.');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = '저장 중…';
    try {
      const result = await callServer('updateHousemanOrder', state.token, {
        orderId: item.recordId,
        rowNumber: Number(item.rowNumber || 0),
        expectedVersion: Number(item.version || 0),
        action: 'EDIT',
        part,
        requester: String($('monthlyManageRequester')?.value || '').trim(),
        note: String($('monthlyManageNote')?.value || '').trim(),
        items,
        important: Boolean($('monthlyManageImportant')?.checked),
        handover: Boolean($('monthlyManageHandover')?.checked)
      });
      if (!result?.ok) throw new Error(result?.message || '오더 내용을 수정하지 못했습니다.');
      void syncRealtimeHousemanEditedContent_(result.order);
      closeModal();
      showToast(`${item.roomNo || ''}호 오더 내용을 수정했습니다.`);
      await loadMonthlyHistory({ page: Number(state.monthly.page || 1), preserveTable: true });
    } catch (error) {
      showToast(error?.message || '오더 수정 오류');
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function assignMonthlyHousemanManagedOrder_(item, button) {
    const employeeNo = String($('monthlyManageAssignee')?.value || '').trim();
    if (!employeeNo) return showToast('배정할 하우스맨을 선택하세요.');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = '배정 중…';
    const sourceOrder = {
      orderId: item.recordId,
      rowNumber: Number(item.rowNumber || 0),
      version: Number(item.version || 0),
      roomNo: item.roomNo,
      businessDate: item.businessDate,
      site: item.site,
      assignedEmployeeNo: item.assignedEmployeeNo || ''
    };
    try {
      if (!novaRealtime_.configLoaded) await initNovaRealtime_();
      let mirrored = null;
      if (novaRealtimeIsEnabled_()) {
        try {
          await novaRealtimeAssignHousemanOrder_(sourceOrder, employeeNo);
          mirrored = await mirrorRealtimeHousemanAssignmentToSheet_(sourceOrder, employeeNo);
        } catch (realtimeError) {
          console.warn('[NOVA 월별조회] 하우스맨 DB 수동배정 실패 · Sheet 경로로 전환', realtimeError?.message || realtimeError);
        }
      }
      if (!mirrored?.ok) {
        mirrored = await callServer('assignHousemanOrderFast', state.token, {
          orderId: item.recordId,
          rowNumber: Number(item.rowNumber || 0),
          expectedVersion: Number(item.version || 0),
          employeeNo
        });
        if (!mirrored?.ok) throw new Error(mirrored?.message || '직원 배정에 실패했습니다.');
        void callServer('finalizeHousemanAssignmentAux', state.token, {
          orderId: mirrored.order.orderId,
          rowNumber: Number(mirrored.order.rowNumber || 0),
          employeeNo,
          version: Number(mirrored.version || 0)
        }).catch(error => console.warn('[NOVA 월별조회] 배정 후속처리 지연', error));
      }
      closeModal();
      showToast(`${item.roomNo || ''}호 담당직원을 변경했습니다.`);
      await loadMonthlyHistory({ page: Number(state.monthly.page || 1), preserveTable: true });
    } catch (error) {
      showToast(error?.message || '직원 배정 오류');
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function cancelMonthlyHousemanRealtimeIfPresent_(orderId) {
    if (!novaRealtime_.configLoaded) await initNovaRealtime_();
    if (!novaRealtimeIsEnabled_()) return null;
    try {
      return await novaMonthlyRealtimeCancelHousemanOrder_(orderId);
    } catch (error) {
      const code = String(error?.code || '').trim().toUpperCase();
      if (Number(error?.status || 0) === 404 || code === 'HOUSEMAN_ORDER_NOT_FOUND') return null;
      throw error;
    }
  }

  async function cancelMonthlyHousemanManagedOrder_(item, button) {
    if (!item?.canCancel) return showToast('현재 상태에서는 오더를 취소할 수 없습니다.');
    if (!window.confirm(`${item.roomNo || '-'}호 오더를 취소할까요?\n\n취소 이력은 월별조회에 남습니다.`)) return;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = '취소 중…';
    try {
      await cancelMonthlyHousemanRealtimeIfPresent_(item.recordId);
      const result = await callServer('cancelMonthlyManagedHousemanOrder', state.token, {
        orderId: item.recordId,
        rowNumber: Number(item.rowNumber || 0)
      });
      if (!result?.ok) throw new Error(result?.message || '오더를 취소하지 못했습니다.');
      closeModal();
      showToast(result.message || `${item.roomNo || ''}호 오더취소 완료`);
      await loadMonthlyHistory({ page: Number(state.monthly.page || 1), preserveTable: true });
    } catch (error) {
      showToast(error?.message || '오더취소 오류');
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function deleteMonthlyHousemanManagedOrder_(item, button) {
    if (!item?.canDelete) return showToast('현재 상태에서는 오더를 삭제할 수 없습니다.');
    if (!window.confirm(`${item.roomNo || '-'}호 오더를 삭제할까요?\n\n목록에서는 제거되지만 감사이력은 보존됩니다.`)) return;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = '삭제 중…';
    try {
      await cancelMonthlyHousemanRealtimeIfPresent_(item.recordId);
      const result = await callServer('deleteMonthlyHousemanOrder', state.token, {
        orderId: item.recordId,
        rowNumber: Number(item.rowNumber || 0)
      });
      if (!result?.ok) throw new Error(result?.message || '오더를 삭제하지 못했습니다.');
      closeModal();
      showToast(result.message || `${item.roomNo || ''}호 오더 삭제 완료`);
      await loadMonthlyHistory({ page: Number(state.monthly.page || 1), preserveTable: true });
    } catch (error) {
      showToast(error?.message || '오더 삭제 오류');
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function cancelMonthlyHousemanOrder_(button) { // (이전 등록취소 버튼 호환)
    const orderId = String(button?.dataset?.monthlyOrderCancel || '').trim();
    const item = monthlyHousemanManageItem_(orderId);
    if (!item) return showToast('관리할 오더를 찾을 수 없습니다.');
    return deleteMonthlyHousemanManagedOrder_(item, button);
  }

  async function openMonthlyHousemanPhotoViewer_'''
    text = pattern.sub(replacement, text, count=1)

write(path, text)

print(f'{MARKER} applied')
