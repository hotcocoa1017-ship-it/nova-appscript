/**
 * TEMPORARY DIAGNOSTIC ONLY — never merge to main.
 * Benchmarks the existing HousemanRequestPhoto save path on Apps Script HEAD.
 * Creates one isolated HISTORY row and Drive folder, then removes both.
 */
function diagnoseHousemanPhotoSaveSpeed20260905() {
  const startedAt = Date.now();
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const index = getUserIndex_();
  const users = Object.values((index && index.byEmployeeNo) || {});
  let user = null;
  for (const candidate of users) {
    const role = String(candidate && candidate.role || '').trim().toUpperCase();
    const employeeNo = String(candidate && candidate.employeeNo || '').trim();
    const site = String(candidate && candidate.defaultSite || '').trim();
    if (!employeeNo || !site || !['PUBLIC', 'QM', 'ROOMMAID'].includes(role)) continue;
    const active = getActiveUserByEmployeeNo_(employeeNo);
    if (active && String(active.role || '').trim().toUpperCase() === role) {
      user = active;
      break;
    }
  }
  if (!user) throw new Error('사진 저장 진단에 사용할 활성 모바일 계정을 찾지 못했습니다.');

  const role = String(user.role || '').trim().toUpperCase();
  const site = String(user.defaultSite || '').trim();
  const token = createLoginToken_(user.employeeNo, site);
  const stamp = Utilities.formatDate(new Date(), NOVA.TIMEZONE, 'yyyyMMddHHmmss');
  const businessDate = `PHOTO_DIAG_${stamp}`;
  const roomNo = `D${stamp.slice(-6)}`;
  const orderId = `HO-PHOTO-DIAG-${stamp}`;
  const createdFileIds = [];
  let insertedRowNumber = 0;

  function makePayloadBytes_(size) {
    const target = Math.max(1024, Number(size || 0));
    const chunk = 'NOVA_PHOTO_SPEED_DIAG_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    let text = '';
    while (text.length < target) text += chunk;
    return Utilities.base64Encode(Utilities.newBlob(text.slice(0, target)).getBytes());
  }

  function createDiagOrder_() {
    const now = nowText_();
    const detail = {
      items: [{ name: 'PHOTO_SPEED_DIAG', quantity: 1 }],
      requester: 'PHOTO_SPEED_DIAG',
      requestSource: role,
      createdFrom: 'MOBILE',
      assignmentMode: 'UNASSIGNED',
      photos: []
    };
    const row = createRowByHeaders_(sheet, {
      '기록ID': orderId,
      '기록구분': NOVA.RECORD_TYPES.HOUSEMAN_ORDER,
      '업무일자': businessDate,
      '사업장': site,
      '객실번호': roomNo,
      '처리상태': 'REGISTERED',
      '세부내용JSON': JSON.stringify(detail),
      '등록사번': user.employeeNo,
      '등록일시': now,
      '수정일시': now,
      '파트': '습득물',
      '품목': 'PHOTO_SPEED_DIAG',
      '수량': 1,
      '추가내용': '',
      '요청자': 'PHOTO_SPEED_DIAG',
      '변경버전': 0,
      '삭제여부': 'N'
    });
    const lock = acquireWriteLock_(5000);
    try {
      insertedRowNumber = sheet.getLastRow() + 1;
      ensureSheetRowCapacity_(sheet, insertedRowNumber);
      sheet.getRange(insertedRowNumber, 1, 1, row.length).setValues([row]);
    } finally {
      lock.releaseLock();
    }
  }

  function cleanup_() {
    createdFileIds.forEach(fileId => {
      try { DriveApp.getFileById(fileId).setTrashed(true); } catch (ignore) {}
    });
    try {
      const found = findHousemanOrderRow_(sheet, orderId, insertedRowNumber);
      if (found && String(found.data['기록ID'] || '').trim() === orderId) {
        sheet.deleteRow(found.rowNumber);
      }
    } catch (ignore) {}
    try {
      const props = PropertiesService.getScriptProperties();
      const rootId = props.getProperty(NOVA_HOUSEMAN_REQUEST_PHOTO.ROOT_PROPERTY);
      if (rootId) {
        const root = DriveApp.getFolderById(rootId);
        const folders = root.getFoldersByName(businessDate);
        while (folders.hasNext()) folders.next().setTrashed(true);
      }
    } catch (ignore) {}
  }

  try {
    const setupStartedAt = Date.now();
    createDiagOrder_();
    const setupMs = Date.now() - setupStartedAt;
    const base64_500k = makePayloadBytes_(500000);
    const perPhoto = [];
    const cumulative = {};
    const sequenceStartedAt = Date.now();

    for (let index = 0; index < 5; index += 1) {
      const callStartedAt = Date.now();
      const result = uploadMobileHousemanRequestPhoto(token, {
        orderId,
        rowNumber: insertedRowNumber,
        fileName: `diag_${index + 1}.jpg`,
        mimeType: 'image/jpeg',
        base64: base64_500k
      });
      const wallMs = Date.now() - callStartedAt;
      if (result && result.photo && result.photo.fileId) createdFileIds.push(String(result.photo.fileId));
      const item = {
        index: index + 1,
        ok: Boolean(result && result.ok === true),
        bytes: 500000,
        apiElapsedMs: Number(result && result.performance && result.performance.elapsedMs || wallMs),
        wallMs,
        code: String(result && result.code || ''),
        message: String(result && result.message || '')
      };
      perPhoto.push(item);
      cumulative[String(index + 1)] = Date.now() - sequenceStartedAt;
      if (!item.ok) break;
    }

    const successRows = perPhoto.filter(item => item.ok);
    return {
      ok: true,
      benchmarkComplete: successRows.length === 5,
      successfulPhotos: successRows.length,
      attemptedPhotos: perPhoto.length,
      role,
      payloadBytesPerPhoto: 500000,
      setupMs,
      perPhoto,
      cumulativeMs: cumulative,
      averageSuccessfulApiMs: successRows.length
        ? Math.round(successRows.reduce((sum, item) => sum + item.apiElapsedMs, 0) / successRows.length)
        : 0,
      totalBenchmarkMs: Date.now() - startedAt
    };
  } finally {
    cleanup_();
  }
}
