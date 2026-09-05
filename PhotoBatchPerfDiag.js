/** TEMPORARY DIAGNOSTIC ONLY — never merge to main. */
function diagnoseHousemanPhotoBatchFast20260905() {
  const overallStartedAt = Date.now();
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const users = Object.values((getUserIndex_() && getUserIndex_().byEmployeeNo) || {});
  let user = null;
  for (const candidate of users) {
    const role = String(candidate && candidate.role || '').trim().toUpperCase();
    const employeeNo = String(candidate && candidate.employeeNo || '').trim();
    const site = String(candidate && candidate.defaultSite || '').trim();
    if (!employeeNo || !site || !['ROOMMAID', 'QM', 'PUBLIC'].includes(role)) continue;
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
  const businessDate = `PHOTO_BATCH_DIAG_${stamp}`;
  const roomNo = `B${stamp.slice(-6)}`;
  const orderId = `HO-PHOTO-BATCH-DIAG-${stamp}`;
  let insertedRowNumber = 0;
  const createdFileIds = [];

  function makeBase64_(size) {
    const target = Math.max(1024, Number(size || 0));
    const chunk = 'NOVA_PHOTO_BATCH_FAST_DIAG_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    let text = '';
    while (text.length < target) text += chunk;
    return Utilities.base64Encode(Utilities.newBlob(text.slice(0, target)).getBytes());
  }

  function createOrder_() {
    const now = nowText_();
    const detail = {
      items: [{ name: 'PHOTO_BATCH_FAST_DIAG', quantity: 1 }],
      requester: 'PHOTO_BATCH_FAST_DIAG',
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
      '품목': 'PHOTO_BATCH_FAST_DIAG',
      '수량': 1,
      '추가내용': '',
      '요청자': 'PHOTO_BATCH_FAST_DIAG',
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
        const lock = acquireWriteLock_(5000);
        try { sheet.deleteRow(found.rowNumber); } finally { lock.releaseLock(); }
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
    createOrder_();
    const setupMs = Date.now() - setupStartedAt;
    const base64 = makeBase64_(500000);
    const photos = Array.from({ length: 5 }, (_, index) => ({
      fileName: `diag_${index + 1}.jpg`,
      mimeType: 'image/jpeg',
      base64
    }));

    const callStartedAt = Date.now();
    const result = uploadMobileHousemanRequestPhotos(token, {
      orderId,
      rowNumber: insertedRowNumber,
      photos
    });
    const wallMs = Date.now() - callStartedAt;
    if (result && Array.isArray(result.photos)) {
      result.photos.forEach(photo => {
        if (photo && photo.fileId) createdFileIds.push(String(photo.fileId));
      });
    }
    if (!result || !result.ok) {
      throw new Error(result && result.message ? result.message : '사진 일괄 저장 실패');
    }

    return {
      ok: true,
      role,
      payloadBytesPerPhoto: 500000,
      photoCount: 5,
      setupMs,
      wallMs,
      serverPerformance: result.performance || null,
      photoPerformance: result.photoPerformance || null,
      totalMs: Date.now() - overallStartedAt
    };
  } finally {
    cleanup_();
  }
}

function diagnosePhotoBatchLockProbe20260905() {
  const startedAt = Date.now();
  const lock = LockService.getScriptLock();
  const acquired = lock.tryLock(750);
  const waitMs = Date.now() - startedAt;
  if (acquired) lock.releaseLock();
  return { ok: acquired, acquired, waitMs };
}
