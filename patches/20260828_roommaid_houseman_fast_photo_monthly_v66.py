from pathlib import Path
import re

FILES = {
    'mobile': Path('10_Mobile.js'),
    'monthly': Path('11_Monthly.js'),
    'photo_server': Path('HousemanRequestPhoto.js'),
    'client': Path('Client.html'),
    'photo_client': Path('HousemanRequestPhotoClient.html'),
}
texts = {key: path.read_text(encoding='utf-8') for key, path in FILES.items()}
originals = dict(texts)


def replace_once(key, old, new, label):
    text = texts[key]
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    texts[key] = text.replace(old, new, 1)


def regex_once(key, pattern, repl, label):
    text = texts[key]
    new_text, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    texts[key] = new_text

# -----------------------------------------------------------------------------
# 10_Mobile.js: DB realtime order ID is mirrored to the existing Sheet row only once.
# -----------------------------------------------------------------------------
replace_once(
    'mobile',
"""    const writeLock = acquireWriteLock_();
    let order;
    let version;
    try {
    version = reserveDataVersion_({ lockHeld: true });
    const orderId = `HO-${safe.businessDate.replaceAll('-', '')}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;
    const now = nowText_();
    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
""",
"""    const writeLock = acquireWriteLock_();
    let order;
    let version;
    try {
    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);

    // Realtime 선등록 후 브라우저 재시도에도 같은 오더를 한 번만 Sheet에 미러한다.
    if (safe.realtimeOrderId) {
      const existing = findHousemanOrderRow_(sheet, safe.realtimeOrderId, 0);
      if (existing) {
        const existingOrder = housemanOrderObject_(existing.data, existing.rowNumber);
        return {
          ok: true,
          version: Number(existingOrder.version || 0),
          order: existingOrder,
          mirrorDuplicate: true,
          message: '하우스맨 요청을 등록했습니다.'
        };
      }
    }

    version = reserveDataVersion_({ lockHeld: true });
    const orderId = safe.realtimeOrderId || `HO-${safe.businessDate.replaceAll('-', '')}-${Utilities.getUuid().slice(0, 8).toUpperCase()}`;
    const now = nowText_();
""",
    'mobile realtime order id and dedup mirror'
)

# -----------------------------------------------------------------------------
# 11_Monthly.js: expose only safe photo metadata in monthly rows.
# -----------------------------------------------------------------------------
replace_once(
    'monthly',
"""  let detail = {};
  try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
  const targetEmployeeNo = String(data['대상사번'] || '').trim();
""",
"""  let detail = {};
  try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
  const photos = typeCode === 'HOUSEMAN' && Array.isArray(detail.photos)
    ? detail.photos
        .filter(photo => photo && photo.fileId)
        .slice(0, NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER)
        .map(photo => ({
          fileId: String(photo.fileId || ''),
          name: String(photo.name || ''),
          mimeType: String(photo.mimeType || 'image/jpeg'),
          size: Number(photo.size || 0),
          uploadedAt: String(photo.uploadedAt || '')
        }))
    : [];
  const targetEmployeeNo = String(data['대상사번'] || '').trim();
""",
    'monthly photo metadata extraction'
)
replace_once(
    'monthly',
"""    requester: String(data['요청자'] || detail.requester || '').trim(),
    important: String(data['중요여부'] || '').trim().toUpperCase() === 'Y',
""",
"""    requester: String(data['요청자'] || detail.requester || '').trim(),
    photos,
    photoCount: photos.length,
    important: String(data['중요여부'] || '').trim().toUpperCase() === 'Y',
""",
    'monthly photo metadata response'
)

# -----------------------------------------------------------------------------
# HousemanRequestPhoto.js: ADMIN/ORDER secure viewer/download endpoint.
# -----------------------------------------------------------------------------
photo_viewer_server = r'''
function getHousemanRequestPhoto(token, payload) { // (오더테이커 월별조회 요청사진 확인·다운로드)
  return measureResponse_('getHousemanRequestPhoto', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const fileId = String(safe.fileId || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    if (!orderId || !fileId) throw new Error('사진을 확인할 오더와 파일정보가 없습니다.');

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const orderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
    if (!orderInfo || !orderInfo.data) throw new Error('하우스맨 요청을 찾을 수 없습니다.');
    if (String(orderInfo.data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ORDER) {
      throw new Error('하우스맨 요청 자료가 아닙니다.');
    }
    if (String(orderInfo.data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') {
      throw new Error('삭제된 요청의 사진은 확인할 수 없습니다.');
    }

    let detail = {};
    try { detail = JSON.parse(String(orderInfo.data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
    const photos = Array.isArray(detail.photos) ? detail.photos.filter(photo => photo && photo.fileId) : [];
    const photo = photos.find(item => String(item.fileId || '').trim() === fileId);
    if (!photo) throw new Error('해당 오더에 연결된 사진을 찾을 수 없습니다.');

    let file;
    try { file = DriveApp.getFileById(fileId); } catch (error) { throw new Error('사진 파일을 열 수 없습니다.'); }
    const blob = file.getBlob();
    const bytes = blob.getBytes();
    if (!bytes.length) throw new Error('사진 파일이 비어 있습니다.');
    if (bytes.length > 5 * 1024 * 1024) throw new Error('사진 파일 용량이 너무 큽니다.');

    return {
      ok: true,
      orderId,
      rowNumber: Number(orderInfo.rowNumber || 0),
      photo: {
        fileId,
        name: String(file.getName() || photo.name || 'houseman-request.jpg'),
        mimeType: String(blob.getContentType() || photo.mimeType || 'image/jpeg'),
        size: bytes.length,
        uploadedAt: String(photo.uploadedAt || '')
      },
      base64: Utilities.base64Encode(bytes)
    };
  });
}

'''
replace_once(
    'photo_server',
    "function validateHousemanRequestPhotoOrder_(orderInfo, user) { // (사진 연결 대상 하우스맨 요청 검증)\n",
    photo_viewer_server + "function validateHousemanRequestPhotoOrder_(orderInfo, user) { // (사진 연결 대상 하우스맨 요청 검증)\n",
    'secure monthly photo viewer server insertion'
)

# -----------------------------------------------------------------------------
# Client.html: small targeted styles.
# -----------------------------------------------------------------------------
style_add = r'''
  .monthly-photo-cell { text-align: center; white-space: nowrap; }
  .monthly-photo-button {
    min-height: 32px;
    padding: 0 10px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    background: #fff;
    color: #111827;
    font-size: 12px;
    font-weight: 800;
    cursor: pointer;
  }
  .monthly-photo-button:hover { background: #f8fafc; }
  .monthly-photo-viewer { display: grid; gap: 12px; }
  .monthly-photo-viewer-image-wrap {
    display: grid;
    place-items: center;
    min-height: 280px;
    max-height: 70vh;
    overflow: hidden;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    background: #f8fafc;
  }
  .monthly-photo-viewer-image {
    display: block;
    max-width: 100%;
    max-height: 68vh;
    object-fit: contain;
  }
  .monthly-photo-viewer-meta,
  .monthly-photo-viewer-nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
'''
replace_once(
    'client',
    "</style>\n<script>\n",
    style_add + "</style>\n<script>\n",
    'monthly photo styles'
)

# Fast ROOMMAID order helper + replace only mobile request submit function.
mobile_fast_block = r'''  async function mirrorRoommaidHousemanRequestToSheet_(mirrorPayload, attempt = 0) { // (Realtime 오더 기존 이력·Telegram 백그라운드 보존)
    try {
      const result = await callServer('createMobileHousemanRequest', state.token, mirrorPayload);
      if (!result?.ok) throw new Error(result?.message || '하우스맨 요청 이력 동기화에 실패했습니다.');
      return result;
    } catch (error) {
      if (attempt < 3) {
        await novaRealtimeSleep_([600, 1600, 3600, 7000][attempt] || 7000);
        return mirrorRoommaidHousemanRequestToSheet_(mirrorPayload, attempt + 1);
      }
      console.error('[NOVA Realtime] 룸메이드 하우스맨 오더 Sheet 미러 실패:', error);
      setSyncStatus('하우스맨 요청 DB 등록완료 · 기존 이력 동기화 재확인 필요');
      throw error;
    }
  }

  async function createRoommaidHousemanRequestFast_(payload) { // (룸메이드 오더 PostgreSQL 선확정·Sheet 후행)
    const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
    if (role !== 'ROOMMAID') {
      const legacy = await callServer('createMobileHousemanRequest', state.token, payload);
      return Object.assign({}, legacy || {}, { realtime: false, mirrorPromise: Promise.resolve(legacy) });
    }

    if (!novaRealtime_.configLoaded) await initNovaRealtime_();
    if (!novaRealtimeIsEnabled_()) {
      const legacy = await callServer('createMobileHousemanRequest', state.token, payload);
      return Object.assign({}, legacy || {}, { realtime: false, mirrorPromise: Promise.resolve(legacy) });
    }

    const realtimePayload = Object.assign({}, payload || {}, {
      assignmentMode: 'UNASSIGNED',
      assignedEmployeeNo: '',
      requester: state.bootstrap?.user?.name || '',
      handover: false
    });
    const realtime = await novaRealtimeCreateHousemanOrder_(realtimePayload);
    const mirrorPayload = Object.assign({}, realtime.mirrorPayload || realtimePayload, {
      realtimeOrderId: realtime.orderId || realtime.order?.orderId || '',
      requester: state.bootstrap?.user?.name || '',
      requestSource: 'ROOMMAID',
      createdFrom: 'MOBILE',
      assignmentMode: 'UNASSIGNED',
      handover: false
    });
    const mirrorPromise = mirrorRoommaidHousemanRequestToSheet_(mirrorPayload);
    // 사진이 없는 일반 등록은 Sheet/Telegram 저장을 사용자 응답과 분리한다.
    void mirrorPromise.catch(() => null);
    return {
      ok: true,
      realtime: true,
      order: realtime.order,
      version: Number(realtime.order?.version || realtime.version || 0),
      timing: realtime.timing || {},
      mirrorPayload,
      mirrorPromise,
      message: '하우스맨 요청을 등록했습니다.'
    };
  }
  window.novaCreateRoommaidHousemanRequestFast_ = createRoommaidHousemanRequestFast_;

  function openMobileHousemanRequest_(roomNo) { // (모바일 하우스맨 요청 등록창)
    const parts = state.mobile.data?.codes?.orderParts || [];
    const itemSuggestions = state.mobile.data?.codes?.orderItems || [];
    const itemDatalist = `<datalist id="mobileHousemanItemSuggestions">${itemSuggestions.map(item => `<option value="${escapeAttr(item.label)}"></option>`).join('')}</datalist>`;
    openModal(`<div class="modal-card"><div class="modal-header"><h2>${escapeHtml(roomNo)} 하우스맨 요청</h2><button class="modal-close" data-close-modal>×</button></div><div class="modal-body">${itemDatalist}<div class="modal-grid"><label class="modal-field"><span>파트</span><select id="mobileRequestPart"><option value="">선택</option>${parts.map(part => `<option value="${escapeAttr(part.label)}">${escapeHtml(part.label)}</option>`).join('')}</select></label><label class="modal-field"><span>수량</span><input id="mobileRequestQty" type="number" min="1" max="99" value="1"></label><label class="modal-field full"><span>품목</span><input id="mobileRequestItem" list="mobileHousemanItemSuggestions" placeholder="예: 타월, 생수"></label><label class="modal-field full"><span>추가내용</span><textarea id="mobileRequestNote" placeholder="필요한 내용을 입력하세요."></textarea></label></div><div class="modal-actions"><button id="mobileRequestSubmit" class="action-button primary" type="button">요청 등록</button></div></div></div>`);
    $('mobileRequestSubmit').addEventListener('click', async event => {
      const part = $('mobileRequestPart').value;
      const item = $('mobileRequestItem').value.trim();
      if (!part || !item) return showToast('파트와 품목을 입력하세요.');
      const payload = {
        businessDate: state.mobile.businessDate, site: state.mobile.site, roomNo, part,
        items: [{ name: item, quantity: clampQuantity($('mobileRequestQty').value) }],
        note: $('mobileRequestNote').value.trim(), requester: state.bootstrap.user.name
      };
      const role = String(state.mobile.data?.role || state.bootstrap?.user?.role || '').trim().toUpperCase();
      if (role !== 'ROOMMAID') {
        closeModal();
        await runMobileAction_('createMobileHousemanRequest', payload, event.currentTarget);
        return;
      }

      const button = event.currentTarget;
      const clickedAt = performance.now();
      button.disabled = true;
      button.textContent = '등록 중…';
      try {
        const result = await createRoommaidHousemanRequestFast_(payload);
        if (!result?.ok) throw new Error(result?.message || '하우스맨 요청을 등록하지 못했습니다.');
        closeModal();
        const elapsed = Math.round(performance.now() - clickedAt);
        showToast(result.message || '하우스맨 요청을 등록했습니다.');
        setSyncStatus(`룸메이드 오더 ${result.realtime ? 'Realtime' : '기존경로'} ${elapsed}ms`);
      } catch (error) {
        showToast(error?.message || '하우스맨 요청 등록 오류');
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = '요청 등록';
        }
      }
    });
  }

'''
regex_once(
    'client',
    r"  function openMobileHousemanRequest_\(roomNo\) \{.*?\n  \}\n\n  function startMobileSync\(\)",
    mobile_fast_block + "  function startMobileSync()",
    'mobile houseman fast create client block'
)

# Monthly header / loading colspans.
replace_once(
    'client',
    '<thead><tr><th>업무일자</th><th>구분</th><th>사업장</th><th>객실</th><th>담당자</th><th>상태</th><th>업무내용</th><th>등록/시작</th><th>완료</th><th>소요</th></tr></thead>',
    '<thead><tr><th>업무일자</th><th>구분</th><th>사업장</th><th>객실</th><th>담당자</th><th>상태</th><th>업무내용</th><th>사진</th><th>등록/시작</th><th>완료</th><th>소요</th></tr></thead>',
    'monthly table photo header'
)
replace_once(
    'client',
    '<tbody id="monthlyTableBody"><tr><td colspan="10" class="table-empty">조회 데이터를 불러오는 중입니다.</td></tr></tbody>',
    '<tbody id="monthlyTableBody"><tr><td colspan="11" class="table-empty">조회 데이터를 불러오는 중입니다.</td></tr></tbody>',
    'monthly initial colspan'
)
replace_once(
    'client',
    'if ($(\'monthlyTableBody\')) $(\'monthlyTableBody\').innerHTML = `<tr><td colspan="10" class="table-empty">${periodLabel} 데이터를 불러오는 중입니다.</td></tr>`;',
    'if ($(\'monthlyTableBody\')) $(\'monthlyTableBody\').innerHTML = `<tr><td colspan="11" class="table-empty">${periodLabel} 데이터를 불러오는 중입니다.</td></tr>`;',
    'monthly loading colspan'
)
replace_once(
    'client',
    'if ($(\'monthlyTableBody\')) $(\'monthlyTableBody\').innerHTML = `<tr><td colspan="10" class="table-empty error">${escapeHtml(error?.message || \'통합조회 오류\')}</td></tr>`;',
    'if ($(\'monthlyTableBody\')) $(\'monthlyTableBody\').innerHTML = `<tr><td colspan="11" class="table-empty error">${escapeHtml(error?.message || \'통합조회 오류\')}</td></tr>`;',
    'monthly error colspan'
)

monthly_render_block = r'''  function renderMonthlyTable_(items) { // (월별·일별 이력 목록·하우스맨 사진보기)
    if (!items.length) {
      $('monthlyTableBody').innerHTML = '<tr><td colspan="11" class="table-empty">선택한 조건의 이력이 없습니다.</td></tr>';
      return;
    }
    $('monthlyTableBody').innerHTML = items.map(item => `
      <tr>
        <td>${escapeHtml(item.businessDate)}</td>
        <td><span class="monthly-type type-${escapeAttr(item.typeCode)}">${escapeHtml(item.typeLabel)}</span></td>
        <td>${escapeHtml(item.site || '-')}</td>
        <td class="room-cell">${escapeHtml(item.roomNo || '-')}</td>
        <td>${escapeHtml(item.employeeDisplay || '-')}</td>
        <td><span class="monthly-status">${escapeHtml(item.statusLabel || '-')}</span></td>
        <td class="monthly-detail" title="${escapeAttr(item.detailText || '')}">${escapeHtml(item.detailText || '-')}</td>
        <td class="monthly-photo-cell">${item.typeCode === 'HOUSEMAN' && Number(item.photoCount || 0) > 0 ? `<button class="monthly-photo-button" type="button" data-monthly-photo-order="${escapeAttr(item.recordId)}">사진보기</button>` : '-'}</td>
        <td>${escapeHtml(item.startedAt || item.acceptedAt || item.registeredAt || '-')}</td>
        <td>${escapeHtml(item.completedAt || '-')}</td>
        <td>${formatMonthlyMinutes_(item.durationMinutes)}</td>
      </tr>`).join('');
    $('monthlyTableBody').querySelectorAll('[data-monthly-photo-order]').forEach(button => {
      button.addEventListener('click', () => openMonthlyHousemanPhotoViewer_(button.dataset.monthlyPhotoOrder, 0));
    });
  }

  async function openMonthlyHousemanPhotoViewer_(orderId, index = 0) { // (월별조회 사진보기·다운로드)
    const item = (state.monthly.data?.items || []).find(row => String(row.recordId || '') === String(orderId || ''));
    const photos = Array.isArray(item?.photos) ? item.photos : [];
    if (!item || !photos.length) return showToast('확인할 요청사진이 없습니다.');
    const safeIndex = Math.max(0, Math.min(photos.length - 1, Number(index || 0)));
    openModal(`
      <div class="modal-card monthly-photo-modal">
        <div class="modal-header"><h2>${escapeHtml(item.roomNo || '-')} 요청사진</h2><button class="modal-close" type="button" data-close-modal>×</button></div>
        <div class="modal-body"><div id="monthlyHousemanPhotoViewerBody" class="monthly-photo-viewer"><div class="settings-loading">사진을 불러오는 중입니다.</div></div></div>
      </div>`);
    await loadMonthlyHousemanPhotoViewer_(item, safeIndex);
  }

  async function loadMonthlyHousemanPhotoViewer_(item, index) { // (사진 한 장씩 지연 로드)
    const root = $('monthlyHousemanPhotoViewerBody');
    const photos = Array.isArray(item?.photos) ? item.photos : [];
    if (!root || !photos.length) return;
    const safeIndex = Math.max(0, Math.min(photos.length - 1, Number(index || 0)));
    const photo = photos[safeIndex];
    root.innerHTML = '<div class="settings-loading">사진을 불러오는 중입니다.</div>';
    try {
      const result = await callServer('getHousemanRequestPhoto', state.token, {
        orderId: item.recordId,
        rowNumber: Number(item.rowNumber || 0),
        fileId: photo.fileId
      });
      if (!result?.ok || !result.base64) throw new Error(result?.message || '사진을 불러오지 못했습니다.');
      if (!$('monthlyHousemanPhotoViewerBody')) return;
      const mimeType = String(result.photo?.mimeType || 'image/jpeg');
      const fileName = String(result.photo?.name || `houseman-photo-${safeIndex + 1}.jpg`);
      root.innerHTML = `
        <div class="monthly-photo-viewer-nav">
          <button id="monthlyPhotoPrev" class="secondary-button" type="button"${safeIndex <= 0 ? ' disabled' : ''}>이전</button>
          <strong>${safeIndex + 1} / ${photos.length}</strong>
          <button id="monthlyPhotoNext" class="secondary-button" type="button"${safeIndex >= photos.length - 1 ? ' disabled' : ''}>다음</button>
        </div>
        <div class="monthly-photo-viewer-image-wrap"><img class="monthly-photo-viewer-image" src="data:${escapeAttr(mimeType)};base64,${result.base64}" alt="${escapeAttr(fileName)}"></div>
        <div class="monthly-photo-viewer-meta"><span>${escapeHtml(fileName)}</span><button id="monthlyPhotoDownload" class="action-button primary" type="button">다운로드</button></div>`;
      $('monthlyPhotoPrev')?.addEventListener('click', () => loadMonthlyHousemanPhotoViewer_(item, safeIndex - 1));
      $('monthlyPhotoNext')?.addEventListener('click', () => loadMonthlyHousemanPhotoViewer_(item, safeIndex + 1));
      $('monthlyPhotoDownload')?.addEventListener('click', () => downloadMonthlyHousemanPhoto_(result));
    } catch (error) {
      if (root) root.innerHTML = `<div class="settings-loading error">${escapeHtml(error?.message || '사진 조회 오류')}</div>`;
    }
  }

  function downloadMonthlyHousemanPhoto_(result) { // (조회한 사진파일 브라우저 다운로드)
    try {
      const binary = window.atob(String(result?.base64 || ''));
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      const blob = new Blob([bytes], { type: String(result?.photo?.mimeType || 'image/jpeg') });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = String(result?.photo?.name || 'houseman-request.jpg');
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (error) {
      showToast(error?.message || '사진 다운로드 오류');
    }
  }

'''
regex_once(
    'client',
    r"  function renderMonthlyTable_\(items\) \{.*?\n  \}\n\n  function renderMonthlyPagination_",
    monthly_render_block + "  function renderMonthlyPagination_",
    'monthly photo table and viewer client'
)

# -----------------------------------------------------------------------------
# HousemanRequestPhotoClient.html: realtime order returns immediately; Sheet/photo continues in background.
# -----------------------------------------------------------------------------
photo_submit_block = r'''  async function submitHousemanRequestWithPhotos_(button) { // (Realtime 오더 즉시확정 후 사진은 후행 저장)
    if (!activeRoomNo) throw new Error('요청 객실번호를 확인하지 못했습니다. 요청창을 닫고 다시 열어 주세요.');
    const token = String(localStorage.getItem('novaToken') || '').trim();
    if (!token) throw new Error('로그인 정보가 없습니다. 다시 로그인해 주세요.');

    const partEl = document.getElementById('mobileRequestPart');
    const itemEl = document.getElementById('mobileRequestItem');
    const qtyEl = document.getElementById('mobileRequestQty');
    const noteEl = document.getElementById('mobileRequestNote');
    const dateEl = document.getElementById('mobileDate');
    const siteEl = document.getElementById('mobileSite');
    const part = String(partEl && partEl.value || '').trim();
    const item = String(itemEl && itemEl.value || '').trim();
    const businessDate = String(dateEl && dateEl.value || '').trim();
    const site = String(siteEl && siteEl.value || '').trim();
    if (!part || !item) throw new Error('파트와 품목을 입력하세요.');
    if (!businessDate) throw new Error('업무일자를 확인하지 못했습니다.');

    setHousemanPhotoSubmitBusy_(button, true, '사진 준비 중…');
    await photoPreparePromise;
    const photos = preparedPhotos.slice();
    if (!photos.length) {
      if (photoPrepareError) throw photoPrepareError;
      throw new Error('사진을 다시 촬영하거나 선택해 주세요.');
    }
    if (photos.length > maxPhotosAllowed) throw new Error(`사진은 최대 ${maxPhotosAllowed}장까지 등록할 수 있습니다.`);

    const createPayload = {
      businessDate,
      site,
      roomNo: activeRoomNo,
      part,
      items: [{ name: item, quantity: clampHousemanPhotoQuantity_(qtyEl && qtyEl.value) }],
      note: String(noteEl && noteEl.value || '').trim()
    };
    setHousemanPhotoSubmitBusy_(button, true, '요청 등록 중…');
    const fastCreate = typeof window.novaCreateRoommaidHousemanRequestFast_ === 'function'
      ? window.novaCreateRoommaidHousemanRequestFast_
      : null;
    const createResult = fastCreate
      ? await fastCreate(createPayload)
      : await callCreateMobileHousemanRequestServer_(token, createPayload);
    if (!createResult || !createResult.ok) {
      throw new Error(createResult && createResult.message ? createResult.message : '하우스맨 요청을 등록하지 못했습니다.');
    }

    const order = createResult.order || {};
    const orderId = String(order.orderId || '').trim();
    if (!orderId) throw new Error('사진 연결용 요청번호를 확인하지 못했습니다.');

    // 오더 등록 반응은 DB 확정 시점에서 끝내고, 기존 Sheet/사진 저장은 사용자 대기와 분리한다.
    closeHousemanPhotoModal_();
    showHousemanPhotoToast_(`하우스맨 요청 등록 완료 · 사진 ${photos.length}장 저장 중…`, false);

    let mirrorResult = createResult;
    if (createResult.mirrorPromise && typeof createResult.mirrorPromise.then === 'function') {
      try {
        mirrorResult = await createResult.mirrorPromise;
      } catch (error) {
        showHousemanPhotoToast_(`요청은 등록되었습니다. 사진 저장 준비 오류 · ${error?.message || '이력 동기화 실패'}`, true);
        return;
      }
    }
    if (!mirrorResult?.ok) {
      showHousemanPhotoToast_('요청은 등록되었습니다. 사진 저장 준비에 실패했습니다.', true);
      return;
    }

    const sheetOrder = mirrorResult.order || order;
    let savedCount = 0;
    const failedMessages = [];
    for (let index = 0; index < photos.length; index += 1) {
      const photo = photos[index];
      try {
        const uploadResult = await callUploadHousemanRequestPhotoServer_(token, {
          orderId,
          rowNumber: Number(sheetOrder.rowNumber || 0),
          fileName: `${String(index + 1).padStart(2, '0')}_${photo.fileName}`,
          mimeType: photo.mimeType,
          base64: photo.base64
        });
        if (uploadResult && uploadResult.ok) savedCount += 1;
        else failedMessages.push(uploadResult && uploadResult.message ? uploadResult.message : `사진 ${index + 1} 저장 오류`);
      } catch (error) {
        failedMessages.push(error && error.message ? error.message : `사진 ${index + 1} 저장 오류`);
      }
    }

    if (savedCount !== photos.length) {
      showHousemanPhotoToast_(`하우스맨 요청 등록완료 · 사진 ${savedCount}/${photos.length}장 저장${failedMessages.length ? ` · ${failedMessages[0]}` : ''}`, true);
      return;
    }
    showHousemanPhotoToast_(`하우스맨 요청과 사진 ${savedCount}장을 저장했습니다.`, false);
  }

'''
regex_once(
    'photo_client',
    r"  async function submitHousemanRequestWithPhotos_\(button\) \{.*?\n  \}\n\n  function callHousemanPhotoCapabilityServer_",
    photo_submit_block + "  function callHousemanPhotoCapabilityServer_",
    'photo submission realtime split'
)

# Final safety/scope guards.
for key, text in texts.items():
    if text == originals[key]:
        raise SystemExit(f'PATCH_ERROR: expected source change missing: {key}')

required_tokens = {
    'mobile': ['safe.realtimeOrderId', 'mirrorDuplicate', 'CREATED_MOBILE'],
    'monthly': ['photoCount: photos.length', 'NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER'],
    'photo_server': ["function getHousemanRequestPhoto(token, payload)", "requireRole_(token, ['ADMIN', 'ORDER'])", 'DriveApp.getFileById(fileId)'],
    'client': ['createRoommaidHousemanRequestFast_', 'data-monthly-photo-order', '사진보기', "callServer('getHousemanRequestPhoto'", 'downloadMonthlyHousemanPhoto_'],
    'photo_client': ['novaCreateRoommaidHousemanRequestFast_', '사진 저장 중', 'mirrorPromise'],
}
for key, tokens in required_tokens.items():
    for token in tokens:
        if token not in texts[key]:
            raise SystemExit(f'PATCH_ERROR: {key} required token missing: {token}')

# Explicitly preserve unrelated fast paths and role handling.
for token in ['QM_START', 'QM_COMPLETE', 'CLEANING_START', 'CLEANING_COMPLETE']:
    if token not in texts['client']:
        raise SystemExit(f'PATCH_ERROR: protected Client fast path missing: {token}')
for token in ["['ROOMMAID', 'QM']", 'queueHousemanOrderTelegram_', 'appendHousemanAudit_']:
    if token not in texts['mobile']:
        raise SystemExit(f'PATCH_ERROR: protected mobile behavior missing: {token}')

for key, path in FILES.items():
    path.write_text(texts[key], encoding='utf-8')

print('ROOMMAID_HOUSEMAN_FAST_PHOTO_MONTHLY_V66_OK')
print('Changed: 10_Mobile.js, 11_Monthly.js, HousemanRequestPhoto.js, Client.html, HousemanRequestPhotoClient.html only')
print('Roommaid create: PostgreSQL response first; Sheet/audit/Telegram mirror background')
print('Photo create: modal closes after order DB confirmation; photos persist after Sheet mirror')
print('Monthly: clean 사진보기 button; secure ADMIN/ORDER view + download')
print('Existing QM/cleaning/houseman processing paths preserved')
