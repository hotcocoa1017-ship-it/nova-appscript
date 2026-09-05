/** TEMPORARY DIAGNOSTIC ONLY — never merge to main. */
const NOVA_PHOTO_BATCH_DIAG_CONTEXT_KEY_ = 'NOVA_PHOTO_BATCH_DIAG_CTX_20260905';

function diagnoseHousemanPhotoBatchPrepare20260905() {
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

  // 실제 운영용 전용 헤더를 먼저 준비합니다. 이후 사진 저장에는 전역락이 필요하지 않습니다.
  const columnSetup = ensureHousemanRequestPhotoMetadataColumn_();
  NOVA_RUNTIME_CACHE_.headerMaps = {};

  const role = String(user.role || '').trim().toUpperCase();
  const site = String(user.defaultSite || '').trim();
  const stamp = Utilities.formatDate(new Date(), NOVA.TIMEZONE, 'yyyyMMddHHmmss');
  const businessDate = `PHOTO_BATCH_DIAG_${stamp}`;
  const roomNo = `B${stamp.slice(-6)}`;
  const orderId = `HO-PHOTO-BATCH-DIAG-${stamp}`;
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

  let rowNumber = 0;
  const lock = acquireWriteLock_(5000);
  try {
    rowNumber = sheet.getLastRow() + 1;
    ensureSheetRowCapacity_(sheet, rowNumber);
    sheet.getRange(rowNumber, 1, 1, row.length).setValues([row]);
  } finally {
    lock.releaseLock();
  }

  const context = {
    employeeNo: user.employeeNo,
    role,
    site,
    businessDate,
    roomNo,
    orderId,
    rowNumber,
    createdFileIds: []
  };
  PropertiesService.getScriptProperties().setProperty(NOVA_PHOTO_BATCH_DIAG_CONTEXT_KEY_, JSON.stringify(context));
  return { ok: true, context: { role, site, businessDate, roomNo, orderId, rowNumber }, columnSetup };
}

function diagnoseHousemanPhotoBatchFast20260905() {
  const overallStartedAt = Date.now();
  const context = readPhotoBatchDiagContext_();
  const user = getActiveUserByEmployeeNo_(context.employeeNo);
  if (!user) throw new Error('진단 사용자 계정을 다시 확인할 수 없습니다.');
  const token = createLoginToken_(user.employeeNo, context.site);

  const target = 500000;
  const chunk = 'NOVA_PHOTO_BATCH_FAST_DIAG_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let text = '';
  while (text.length < target) text += chunk;
  const base64 = Utilities.base64Encode(Utilities.newBlob(text.slice(0, target)).getBytes());
  const photos = Array.from({ length: 5 }, (_, index) => ({
    clientPhotoId: `diag_photo_${index + 1}`,
    fileName: `diag_${index + 1}.jpg`,
    mimeType: 'image/jpeg',
    base64
  }));

  const callStartedAt = Date.now();
  const result = uploadMobileHousemanRequestPhotos(token, {
    orderId: context.orderId,
    rowNumber: context.rowNumber,
    photos
  });
  const wallMs = Date.now() - callStartedAt;
  if (!result || !result.ok) {
    throw new Error(result && result.message ? result.message : '사진 일괄 저장 실패');
  }

  context.createdFileIds = (Array.isArray(result.photos) ? result.photos : [])
    .map(photo => String(photo && photo.fileId || '').trim())
    .filter(Boolean);
  PropertiesService.getScriptProperties().setProperty(NOVA_PHOTO_BATCH_DIAG_CONTEXT_KEY_, JSON.stringify(context));

  return {
    ok: true,
    role: context.role,
    payloadBytesPerPhoto: 500000,
    photoCount: 5,
    wallMs,
    serverPerformance: result.performance || null,
    photoPerformance: result.photoPerformance || null,
    totalMs: Date.now() - overallStartedAt
  };
}

function diagnosePhotoBatchLockProbe20260905() {
  const startedAt = Date.now();
  const lock = LockService.getScriptLock();
  const acquired = lock.tryLock(750);
  const waitMs = Date.now() - startedAt;
  if (acquired) lock.releaseLock();
  return { ok: acquired, acquired, waitMs };
}

function diagnoseHousemanPhotoBatchCleanup20260905() {
  const props = PropertiesService.getScriptProperties();
  const context = readPhotoBatchDiagContext_();
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  (context.createdFileIds || []).forEach(fileId => {
    try { DriveApp.getFileById(fileId).setTrashed(true); } catch (ignore) {}
  });
  try {
    const found = findHousemanOrderRow_(sheet, context.orderId, context.rowNumber);
    if (found && String(found.data['기록ID'] || '').trim() === context.orderId) {
      const lock = acquireWriteLock_(5000);
      try { sheet.deleteRow(found.rowNumber); } finally { lock.releaseLock(); }
    }
  } catch (ignore) {}
  try {
    const rootId = props.getProperty(NOVA_HOUSEMAN_REQUEST_PHOTO.ROOT_PROPERTY);
    if (rootId) {
      const root = DriveApp.getFolderById(rootId);
      const folders = root.getFoldersByName(context.businessDate);
      while (folders.hasNext()) folders.next().setTrashed(true);
    }
  } catch (ignore) {}
  props.deleteProperty(NOVA_PHOTO_BATCH_DIAG_CONTEXT_KEY_);
  return { ok: true, cleaned: true };
}

function readPhotoBatchDiagContext_() {
  const raw = PropertiesService.getScriptProperties().getProperty(NOVA_PHOTO_BATCH_DIAG_CONTEXT_KEY_);
  if (!raw) throw new Error('사진 배치 진단 준비정보가 없습니다.');
  const context = JSON.parse(raw);
  if (!context || !context.orderId || !context.employeeNo || !context.rowNumber) {
    throw new Error('사진 배치 진단 준비정보가 올바르지 않습니다.');
  }
  return context;
}
