from pathlib import Path

MARKER = 'MONTHLY_HOUSEMAN_COLUMNS_V1'
monthly_path = Path('11_Monthly.js')
client_path = Path('Client.html')
monthly = monthly_path.read_text(encoding='utf-8')
client = client_path.read_text(encoding='utf-8')

if MARKER in monthly and MARKER in client:
    print('MONTHLY_HOUSEMAN_COLUMNS_V1 already applied.')
    raise SystemExit(0)

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)

# ---------- 11_Monthly.js: keep existing attribution fields, add display-only registrant/handler identities. ----------
monthly = replace_once(
    monthly,
    "function monthlyHistoryItem_(data, rowNumber, users, orderStatusMap) { // (업무이력 행을 월별조회 객체로 변환)",
    "function monthlyHistoryItem_(data, rowNumber, users, orderStatusMap) { // (업무이력 행을 월별조회 객체로 변환) // MONTHLY_HOUSEMAN_COLUMNS_V1",
    'monthly history marker'
)
monthly = replace_once(
    monthly,
    "  const primaryEmployeeNo = processorEmployeeNo || assignedEmployeeNo || targetEmployeeNo || qmReceiverEmployeeNo;\n  const primaryUser = users[primaryEmployeeNo];\n  const statusCode = String(data['처리상태'] || '').trim().toUpperCase();",
    "  const primaryEmployeeNo = processorEmployeeNo || assignedEmployeeNo || targetEmployeeNo || qmReceiverEmployeeNo;\n  const primaryUser = users[primaryEmployeeNo];\n  const acceptedByEmployeeNo = String(detail.acceptedByEmployeeNo || '').trim(); // MONTHLY_HOUSEMAN_COLUMNS_V1\n  const handlerEmployeeNo = processorEmployeeNo || acceptedByEmployeeNo;\n  const registeredByUser = users[registeredEmployeeNo];\n  const handlerUser = users[handlerEmployeeNo];\n  const statusCode = String(data['처리상태'] || '').trim().toUpperCase();",
    'monthly identity variables'
)
monthly = replace_once(
    monthly,
    "    employeeName: primaryUser ? primaryUser.name : (primaryEmployeeNo || '-'),\n    employeeDisplay: primaryUser ? `${primaryUser.name} (${primaryEmployeeNo})` : (primaryEmployeeNo || '-'),\n    statusCode,",
    "    employeeName: primaryUser ? primaryUser.name : (primaryEmployeeNo || '-'),\n    employeeDisplay: primaryUser ? `${primaryUser.name} (${primaryEmployeeNo})` : (primaryEmployeeNo || '-'),\n    registeredByEmployeeNo: registeredEmployeeNo, // MONTHLY_HOUSEMAN_COLUMNS_V1\n    registeredByName: registeredByUser ? registeredByUser.name : (registeredEmployeeNo || '-'),\n    acceptedByEmployeeNo,\n    handlerEmployeeNo,\n    handlerName: handlerUser ? handlerUser.name : (handlerEmployeeNo || '-'),\n    statusCode,",
    'monthly identity return fields'
)

# ---------- Client.html: houseman-only 12-column layout; roommaid/QM retain existing 11-column layout. ----------
client = replace_once(
    client,
    "            <thead><tr><th>업무일자</th><th>구분</th><th>사업장</th><th>객실</th><th>담당자</th><th>상태</th><th>업무내용</th><th>사진</th><th>등록/시작</th><th>완료</th><th>소요</th></tr></thead>\n            <tbody id=\"monthlyTableBody\"><tr><td colspan=\"11\" class=\"table-empty\">조회 데이터를 불러오는 중입니다.</td></tr></tbody>",
    "            <thead><tr id=\"monthlyTableHeaderRow\"><th>업무일자</th><th>구분</th><th>사업장</th><th>객실</th><th>담당자</th><th>상태</th><th>업무내용</th><th>사진</th><th>등록/시작</th><th>완료</th><th>소요</th></tr></thead>\n            <tbody id=\"monthlyTableBody\"><tr><td colspan=\"11\" class=\"table-empty\">조회 데이터를 불러오는 중입니다.</td></tr></tbody>",
    'monthly header id'
)
client = replace_once(
    client,
    "    bindMonthlyControls_();\n  }\n\n  function bindMonthlyControls_()",
    "    bindMonthlyControls_();\n    renderMonthlyTableHeader_(); // MONTHLY_HOUSEMAN_COLUMNS_V1\n  }\n\n  function bindMonthlyControls_()",
    'initial monthly header render'
)

# Realtime-created houseman row: expose current registrar immediately without waiting for history refresh.
client = replace_once(
    client,
    "      employeeName: assignedName || assignedEmployeeNo || '-',\n      employeeDisplay: assignedEmployeeNo ? `${assignedName || assignedEmployeeNo} (${assignedEmployeeNo})` : '-',\n      statusCode:",
    "      employeeName: assignedName || assignedEmployeeNo || '-',\n      employeeDisplay: assignedEmployeeNo ? `${assignedName || assignedEmployeeNo} (${assignedEmployeeNo})` : '-',\n      registeredByEmployeeNo: String(state.bootstrap?.user?.employeeNo || ''), // MONTHLY_HOUSEMAN_COLUMNS_V1\n      registeredByName: String(state.bootstrap?.user?.name || state.bootstrap?.user?.employeeNo || '-'),\n      acceptedByEmployeeNo: '',\n      handlerEmployeeNo: '',\n      handlerName: '-',\n      statusCode:",
    'monthly realtime item identities'
)

start = client.find("  function renderMonthlyTable_(items) { // (월별·일별 이력 목록·하우스맨 사진보기)")
if start < 0:
    raise SystemExit('renderMonthlyTable_ start anchor not found')
end = client.find("\n\n  async function cancelMonthlyHousemanOrder_", start)
if end < 0:
    raise SystemExit('renderMonthlyTable_ end anchor not found')

new_render = r'''  function renderMonthlyTableHeader_() { // (하우스맨 전용 요청자·등록자·실처리자 열) // MONTHLY_HOUSEMAN_COLUMNS_V1
    const row = $('monthlyTableHeaderRow');
    const houseman = String(state.monthly.type || '').trim().toUpperCase() === 'HOUSEMAN';
    if (row) {
      const headers = houseman
        ? ['업무일자', '구분', '사업장', '객실', '의뢰자(등록)', '담당자(접수.처리)', '상태', '업무내용', '사진', '등록.시작', '완료', '소요']
        : ['업무일자', '구분', '사업장', '객실', '담당자', '상태', '업무내용', '사진', '등록/시작', '완료', '소요'];
      row.innerHTML = headers.map(label => `<th>${escapeHtml(label)}</th>`).join('');
    }
    return houseman ? 12 : 11;
  }

  function renderMonthlyTable_(items) { // (월별·일별 이력 목록·하우스맨 사진보기) // MONTHLY_HOUSEMAN_COLUMNS_V1
    const houseman = String(state.monthly.type || '').trim().toUpperCase() === 'HOUSEMAN';
    const columnCount = renderMonthlyTableHeader_();
    if (!items.length) {
      $('monthlyTableBody').innerHTML = `<tr><td colspan="${columnCount}" class="table-empty">선택한 조건의 이력이 없습니다.</td></tr>`;
      return;
    }
    $('monthlyTableBody').innerHTML = items.map(item => {
      if (houseman) {
        const requester = String(item.requester || '').trim() || '-';
        const registeredByName = String(item.registeredByName || '').trim() || '-';
        const registeredByEmployeeNo = String(item.registeredByEmployeeNo || '').trim();
        const handlerName = String(item.handlerName || '').trim() || '-';
        const handlerEmployeeNo = String(item.handlerEmployeeNo || '').trim();
        return `
          <tr>
            <td>${escapeHtml(item.businessDate)}</td>
            <td><span class="monthly-type type-${escapeAttr(item.typeCode)}">${escapeHtml(item.typeLabel)}</span></td>
            <td>${escapeHtml(item.site || '-')}</td>
            <td class="room-cell">${escapeHtml(item.roomNo || '-')}</td>
            <td><strong>${escapeHtml(requester)}</strong><small>등록 ${escapeHtml(registeredByName)}${registeredByEmployeeNo && registeredByName !== registeredByEmployeeNo ? ` (${escapeHtml(registeredByEmployeeNo)})` : ''}</small></td>
            <td>${handlerName !== '-' ? `<strong>${escapeHtml(handlerName)}</strong>${handlerEmployeeNo && handlerName !== handlerEmployeeNo ? `<small>${escapeHtml(handlerEmployeeNo)}</small>` : ''}` : '-'}</td>
            <td><span class="monthly-status">${escapeHtml(item.statusLabel || '-')}</span>${item.canDelete ? `<button class="monthly-order-cancel" type="button" data-monthly-order-cancel="${escapeAttr(item.recordId)}">등록취소</button>` : ''}</td>
            <td class="monthly-detail" title="${escapeAttr(item.detailText || '')}">${escapeHtml(item.detailText || '-')}</td>
            <td class="monthly-photo-cell">${Number(item.photoCount || 0) > 0 ? `<button class="monthly-photo-button" type="button" data-monthly-photo-order="${escapeAttr(item.recordId)}">사진보기</button>` : '-'}</td>
            <td><span>등록 ${escapeHtml(item.registeredAt || '-')}</span><small>시작 ${escapeHtml(item.startedAt || '-')}</small></td>
            <td>${escapeHtml(item.completedAt || '-')}</td>
            <td>${formatMonthlyMinutes_(item.durationMinutes)}</td>
          </tr>`;
      }
      return `
        <tr>
          <td>${escapeHtml(item.businessDate)}</td>
          <td><span class="monthly-type type-${escapeAttr(item.typeCode)}">${escapeHtml(item.typeLabel)}</span></td>
          <td>${escapeHtml(item.site || '-')}</td>
          <td class="room-cell">${escapeHtml(item.roomNo || '-')}</td>
          <td>${escapeHtml(item.employeeDisplay || '-')}</td>
          <td><span class="monthly-status">${escapeHtml(item.statusLabel || '-')}</span>${item.canDelete ? `<button class="monthly-order-cancel" type="button" data-monthly-order-cancel="${escapeAttr(item.recordId)}">등록취소</button>` : ''}</td>
          <td class="monthly-detail" title="${escapeAttr(item.detailText || '')}">${escapeHtml(item.detailText || '-')}</td>
          <td class="monthly-photo-cell">${item.typeCode === 'HOUSEMAN' && Number(item.photoCount || 0) > 0 ? `<button class="monthly-photo-button" type="button" data-monthly-photo-order="${escapeAttr(item.recordId)}">사진보기</button>` : '-'}</td>
          <td>${escapeHtml(item.startedAt || item.acceptedAt || item.registeredAt || '-')}</td>
          <td>${escapeHtml(item.completedAt || '-')}</td>
          <td>${formatMonthlyMinutes_(item.durationMinutes)}</td>
        </tr>`;
    }).join('');
    $('monthlyTableBody').querySelectorAll('[data-monthly-photo-order]').forEach(button => {
      button.addEventListener('click', () => openMonthlyHousemanPhotoViewer_(button.dataset.monthlyPhotoOrder, 0));
    });
    $('monthlyTableBody').querySelectorAll('[data-monthly-order-cancel]').forEach(button => {
      button.addEventListener('click', () => cancelMonthlyHousemanOrder_(button));
    });
  }'''
client = client[:start] + new_render + client[end:]

# Safety checks
for required in [
    'MONTHLY_HOUSEMAN_COLUMNS_V1',
    'registeredByEmployeeNo',
    'registeredByName',
    'handlerEmployeeNo',
    'handlerName',
    'acceptedByEmployeeNo',
]:
    if required not in monthly:
        raise SystemExit('11_Monthly safety marker missing: ' + required)
for required in [
    'MONTHLY_HOUSEMAN_COLUMNS_V1',
    'monthlyTableHeaderRow',
    '의뢰자(등록)',
    '담당자(접수.처리)',
    '등록.시작',
    'registeredByName',
    'handlerName',
]:
    if required not in client:
        raise SystemExit('Client safety marker missing: ' + required)

monthly_path.write_text(monthly, encoding='utf-8')
client_path.write_text(client, encoding='utf-8')
print('Applied MONTHLY_HOUSEMAN_COLUMNS_V1')
