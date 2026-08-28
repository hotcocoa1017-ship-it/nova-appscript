from pathlib import Path
import subprocess

CLIENT = Path('Client.html')
MONTHLY = Path('11_Monthly.js')

client = CLIENT.read_text(encoding='utf-8')
monthly = MONTHLY.read_text(encoding='utf-8')

# ---------------------------------------------------------
# Client: 월별조회 목록을 등록/삭제 중 비우지 않는 silent refresh
# ---------------------------------------------------------
old_load_head = """  async function loadMonthlyHistory(overrides = {}) { // (월별·일별 이력 서버 조회)
    if (state.monthly.loading) return;
    state.monthly.loading = true;
    const filters = collectMonthlyFilters_(overrides);
    const periodLabel = filters.period === 'DAILY' ? '일별' : '월별';
    if ($('monthlyTableBody')) $('monthlyTableBody').innerHTML = `<tr><td colspan=\"11\" class=\"table-empty\">${periodLabel} 데이터를 불러오는 중입니다.</td></tr>`;
"""
new_load_head = """  async function loadMonthlyHistory(overrides = {}) { // (월별·일별 이력 서버 조회)
    if (state.monthly.loading) return;
    state.monthly.loading = true;
    const preserveTable = Boolean(overrides && overrides.preserveTable);
    const filters = collectMonthlyFilters_(overrides);
    const periodLabel = filters.period === 'DAILY' ? '일별' : '월별';
    if (!preserveTable && $('monthlyTableBody')) $('monthlyTableBody').innerHTML = `<tr><td colspan=\"11\" class=\"table-empty\">${periodLabel} 데이터를 불러오는 중입니다.</td></tr>`;
"""
if 'const preserveTable = Boolean(overrides && overrides.preserveTable);' not in client:
    if client.count(old_load_head) != 1:
        raise SystemExit(f'Client load head target count mismatch: {client.count(old_load_head)}')
    client = client.replace(old_load_head, new_load_head, 1)

old_load_error = """    } catch (error) {
      if ($('monthlyTableBody')) $('monthlyTableBody').innerHTML = `<tr><td colspan=\"11\" class=\"table-empty error\">${escapeHtml(error?.message || '통합조회 오류')}</td></tr>`;
      showToast(error?.message || '통합조회 오류');
"""
new_load_error = """    } catch (error) {
      if (!preserveTable && $('monthlyTableBody')) $('monthlyTableBody').innerHTML = `<tr><td colspan=\"11\" class=\"table-empty error\">${escapeHtml(error?.message || '통합조회 오류')}</td></tr>`;
      showToast(error?.message || '통합조회 오류');
"""
if 'if (!preserveTable && $(\'monthlyTableBody\'))' not in client:
    if client.count(old_load_error) != 1:
        raise SystemExit(f'Client load error target count mismatch: {client.count(old_load_error)}')
    client = client.replace(old_load_error, new_load_error, 1)

# ---------------------------------------------------------
# Client: 월별조회에서 만든 오더임을 태그하고, 성공 후 현재 조회조건 유지
# ---------------------------------------------------------
old_payload_tail = """      requester: String($('monthlyOrderRequester')?.value || '오더테이커'),
      assignmentMode: String($('monthlyOrderAssignmentMode')?.value || 'AUTO'),
      important: Boolean($('monthlyOrderImportant')?.checked),
      handover: Boolean($('monthlyOrderHandover')?.checked)
"""
new_payload_tail = """      requester: String($('monthlyOrderRequester')?.value || '오더테이커'),
      requestSource: 'MONTHLY_HISTORY',
      assignmentMode: String($('monthlyOrderAssignmentMode')?.value || 'AUTO'),
      important: Boolean($('monthlyOrderImportant')?.checked),
      handover: Boolean($('monthlyOrderHandover')?.checked)
"""
if "requestSource: 'MONTHLY_HISTORY'" not in client:
    if client.count(old_payload_tail) != 1:
        raise SystemExit(f'Client monthly payload target count mismatch: {client.count(old_payload_tail)}')
    client = client.replace(old_payload_tail, new_payload_tail, 1)

old_success = """      closeModal();
      state.monthly.site = payload.site;
      sessionStorage.setItem('novaMonthlySite', payload.site);
      if ($('monthlySite')) $('monthlySite').value = payload.site;
      showToast(`${payload.roomNo}호 하우스맨 오더 등록 완료`);
      await loadMonthlyHistory({ page: 1 });
"""
new_success = """      closeModal();
      showToast(`${payload.roomNo}호 하우스맨 오더 등록 완료`);
      await loadMonthlyHistory({ page: 1, preserveTable: true });
"""
if "await loadMonthlyHistory({ page: 1, preserveTable: true });" not in client:
    if client.count(old_success) != 1:
        raise SystemExit(f'Client monthly success target count mismatch: {client.count(old_success)}')
    client = client.replace(old_success, new_success, 1)

# ---------------------------------------------------------
# Client: 상태 칸에 월별조회 직접등록 오더만 등록취소 버튼 표시
# ---------------------------------------------------------
old_status_cell = """        <td><span class=\"monthly-status\">${escapeHtml(item.statusLabel || '-')}</span></td>
"""
new_status_cell = """        <td><span class=\"monthly-status\">${escapeHtml(item.statusLabel || '-')}</span>${item.canDelete ? `<button class=\"monthly-order-cancel\" type=\"button\" data-monthly-order-cancel=\"${escapeAttr(item.recordId)}\">등록취소</button>` : ''}</td>
"""
if 'data-monthly-order-cancel=' not in client:
    if client.count(old_status_cell) != 1:
        raise SystemExit(f'Client monthly status cell target count mismatch: {client.count(old_status_cell)}')
    client = client.replace(old_status_cell, new_status_cell, 1)

old_photo_bind = """    $('monthlyTableBody').querySelectorAll('[data-monthly-photo-order]').forEach(button => {
      button.addEventListener('click', () => openMonthlyHousemanPhotoViewer_(button.dataset.monthlyPhotoOrder, 0));
    });
  }

  async function openMonthlyHousemanPhotoViewer_(orderId, index = 0) { // (월별조회 사진보기·다운로드)
"""
new_photo_bind = """    $('monthlyTableBody').querySelectorAll('[data-monthly-photo-order]').forEach(button => {
      button.addEventListener('click', () => openMonthlyHousemanPhotoViewer_(button.dataset.monthlyPhotoOrder, 0));
    });
    $('monthlyTableBody').querySelectorAll('[data-monthly-order-cancel]').forEach(button => {
      button.addEventListener('click', () => cancelMonthlyHousemanOrder_(button));
    });
  }

  async function cancelMonthlyHousemanOrder_(button) { // (월별조회 직접등록 하우스맨 오더 등록취소)
    const orderId = String(button?.dataset?.monthlyOrderCancel || '').trim();
    const item = (state.monthly.data?.items || []).find(row => String(row.recordId || '') === orderId);
    if (!item || !item.canDelete) return showToast('등록취소할 수 없는 오더입니다.');
    if (!window.confirm(`${item.roomNo || '-'}호 하우스맨 오더를 삭제할까요?\\n\\n접수·처리 시작 전 오더만 삭제할 수 있습니다.`)) return;

    const original = button.textContent;
    button.disabled = true;
    button.textContent = '취소 중…';
    try {
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

  async function openMonthlyHousemanPhotoViewer_(orderId, index = 0) { // (월별조회 사진보기·다운로드)
"""
if 'async function cancelMonthlyHousemanOrder_(button)' not in client:
    if client.count(old_photo_bind) != 1:
        raise SystemExit(f'Client photo bind target count mismatch: {client.count(old_photo_bind)}')
    client = client.replace(old_photo_bind, new_photo_bind, 1)

# CSS는 기존 월별 사진 버튼 스타일 바로 뒤에 최소 추가
css_anchor = """  .monthly-photo-button:hover { background: #f8fafc; }
"""
css_add = """  .monthly-photo-button:hover { background: #f8fafc; }
  .monthly-order-cancel {
    margin-left: 6px;
    min-height: 28px;
    padding: 0 8px;
    border: 1px solid #fecaca;
    border-radius: 7px;
    background: #fff;
    color: #b91c1c;
    font-size: 11px;
    font-weight: 800;
    white-space: nowrap;
    cursor: pointer;
  }
  .monthly-order-cancel:hover { background: #fff7f7; }
  .monthly-order-cancel:disabled { opacity: .55; cursor: default; }
"""
if '.monthly-order-cancel {' not in client:
    if client.count(css_anchor) != 1:
        raise SystemExit(f'Client CSS anchor count mismatch: {client.count(css_anchor)}')
    client = client.replace(css_anchor, css_add, 1)

# ---------------------------------------------------------
# Server: monthly item에 삭제 가능여부 노출
# 월별조회에서 직접 등록 + 아직 접수/처리 전인 건만 가능
# ---------------------------------------------------------
old_return_status = """    statusCode,
    statusLabel,
    detailText: monthlyDetailText_(typeCode, data, detail, statusLabel),
"""
new_return_status = """    statusCode,
    statusLabel,
    requestSource: String(detail.requestSource || '').trim(),
    canDelete: typeCode === 'HOUSEMAN'
      && String(detail.requestSource || '').trim().toUpperCase() === 'MONTHLY_HISTORY'
      && ['REGISTERED', 'ASSIGNED'].includes(statusCode),
    detailText: monthlyDetailText_(typeCode, data, detail, statusLabel),
"""
if 'canDelete: typeCode === \'HOUSEMAN\'' not in monthly:
    if monthly.count(old_return_status) != 1:
        raise SystemExit(f'Monthly return status target count mismatch: {monthly.count(old_return_status)}')
    monthly = monthly.replace(old_return_status, new_return_status, 1)

# ---------------------------------------------------------
# Server: 실제 행 삭제가 아니라 삭제여부=Y 소프트삭제 + 감사이력
# 이미 접수/처리된 건은 서버에서 재검증 후 차단
# ---------------------------------------------------------
server_anchor = """function getMonthlyHousemanOrderOptions(token) { // (월별조회 하우스맨 등록창 코드옵션 직접 조회)
"""
server_function = """function deleteMonthlyHousemanOrder(token, payload) { // (월별조회 직접등록 하우스맨 오더 소프트삭제)
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

      let detail = {};
      try { detail = JSON.parse(String(found.data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
      if (String(detail.requestSource || '').trim().toUpperCase() !== 'MONTHLY_HISTORY') {
        throw new Error('월별조회에서 직접 등록한 오더만 여기서 삭제할 수 있습니다.');
      }

      const statusCode = String(found.data['처리상태'] || '').trim().toUpperCase();
      if (!['REGISTERED', 'ASSIGNED'].includes(statusCode)) {
        throw new Error('이미 접수 또는 처리가 시작된 오더는 삭제할 수 없습니다.');
      }
      if (String(found.data['접수일시'] || '').trim() || String(found.data['처리시작일시'] || '').trim()) {
        throw new Error('이미 접수 또는 처리가 시작된 오더는 삭제할 수 없습니다.');
      }

      const users = getUserIndex_().byEmployeeNo;
      const statusCodeMap = {};
      getCodes_('하우스맨상태').forEach(code => { statusCodeMap[code.code] = code.label; });
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
        reason: 'ORDER_REGISTRATION_CANCELLED'
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
        message: `${String(found.data['객실번호'] || '').trim()}호 오더 등록을 취소했습니다.`
      };
    } finally {
      lock.releaseLock();
    }
  });
}

function getMonthlyHousemanOrderOptions(token) { // (월별조회 하우스맨 등록창 코드옵션 직접 조회)
"""
if 'function deleteMonthlyHousemanOrder(token, payload)' not in monthly:
    if monthly.count(server_anchor) != 1:
        raise SystemExit(f'Monthly delete function anchor count mismatch: {monthly.count(server_anchor)}')
    monthly = monthly.replace(server_anchor, server_function, 1)

required_client = [
    'const preserveTable = Boolean(overrides && overrides.preserveTable);',
    "requestSource: 'MONTHLY_HISTORY'",
    'await loadMonthlyHistory({ page: 1, preserveTable: true });',
    'data-monthly-order-cancel=',
    'async function cancelMonthlyHousemanOrder_(button)',
]
for marker in required_client:
    if marker not in client:
        raise SystemExit(f'Missing Client marker after patch: {marker}')

required_monthly = [
    'function deleteMonthlyHousemanOrder(token, payload)',
    "String(detail.requestSource || '').trim().toUpperCase() === 'MONTHLY_HISTORY'",
    "['REGISTERED', 'ASSIGNED'].includes(statusCode)",
    "'삭제여부': 'Y'",
    "buildHousemanAuditRow_(sheet, current, 'DELETED'",
]
for marker in required_monthly:
    if marker not in monthly:
        raise SystemExit(f'Missing Monthly marker after patch: {marker}')

CLIENT.write_text(client, encoding='utf-8')
MONTHLY.write_text(monthly, encoding='utf-8')

changed = [line.strip() for line in subprocess.check_output(['git', 'diff', '--name-only'], text=True).splitlines() if line.strip()]
allowed = {'Client.html', '11_Monthly.js'}
unexpected = [path for path in changed if path not in allowed]
if unexpected:
    raise SystemExit(f'Unexpected source changes: {unexpected}')

print('MONTHLY_HOUSEMAN_STABLE_LIST_CANCEL_V81_OK')
print('Changed: Client.html, 11_Monthly.js only')
print('Registration keeps current monthly filters/list visible and refreshes silently')
print('Monthly-created REGISTERED/ASSIGNED orders expose a safe soft-delete button')
print('Accepted/processing/completed orders remain protected from deletion')
