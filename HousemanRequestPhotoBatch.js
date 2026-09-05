/**
 * HOUSEMAN_PHOTO_BATCH_FAST_V2
 * 하우스맨 요청/습득물 사진 저장을 운영 쓰기경로와 완전히 분리합니다.
 * - 오더 등록 완료 후 후행 저장 전용
 * - 사진 1~5장을 1회 서버호출로 처리
 * - Drive 파일 생성 중 ScriptLock 사용 안 함
 * - HISTORY의 기존 세부내용JSON을 건드리지 않고 전용 '요청사진JSON' 열만 기록
 * - 사진 저장 경로에서는 ScriptLock을 한 번도 획득하지 않음
 */
const NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_ = '요청사진JSON';
const NOVA_HOUSEMAN_PHOTO_METADATA_VERSION_ = 1;

function uploadMobileHousemanRequestPhotos(token, payload) { // (최대 5장 일괄·무전역락 후행 저장)
  return measureResponse_('uploadMobileHousemanRequestPhotos', () => {
    const startedAt = Date.now();
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const user = auth.user;
    const role = String(user.role || '').trim().toUpperCase();
    if (!['ROOMMAID', 'QM', 'PUBLIC'].includes(role)) {
      throw new Error('하우스맨 요청사진 등록 권한이 없습니다.');
    }

    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    const sourcePhotos = Array.isArray(safe.photos) ? safe.photos : [];
    if (!orderId) throw new Error('하우스맨 요청번호가 없습니다.');
    if (!sourcePhotos.length) throw new Error('저장할 사진이 없습니다.');
    if (sourcePhotos.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
      throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
    }

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const photoColumn = Number(getHeaderMap_(sheet)[NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_] || 0);
    if (!photoColumn) {
      const error = new Error('요청사진 저장영역이 준비되지 않았습니다. 관리자에게 문의하세요.');
      error.code = 'PHOTO_METADATA_COLUMN_MISSING';
      throw error;
    }

    const orderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
    const detail = validateHousemanRequestPhotoOrder_(orderInfo, user);
    const legacyPhotos = Array.isArray(detail.photos)
      ? detail.photos.filter(photo => photo && photo.fileId)
      : [];
    const currentMetadata = readHousemanRequestPhotoMetadata_(orderInfo.data);
    const currentPhotos = currentMetadata.photos;
    const currentClientIds = new Set(currentPhotos.map(photo => String(photo.clientPhotoId || '')).filter(Boolean));

    // 동일 요청의 네트워크 재전송은 이미 저장된 clientPhotoId를 기준으로 중복 생성하지 않습니다.
    const preparedPhotos = sourcePhotos.map((source, index) => {
      const photo = source || {};
      const clientPhotoId = String(photo.clientPhotoId || `photo_${index + 1}`).trim().slice(0, 120);
      const mimeType = String(photo.mimeType || '').trim().toLowerCase();
      if (mimeType !== 'image/jpeg') throw new Error(`사진 ${index + 1}은 JPG 형식이어야 합니다.`);
      const base64 = String(photo.base64 || '').replace(/^data:[^;]+;base64,/, '').trim();
      if (!base64) throw new Error(`사진 ${index + 1} 데이터가 없습니다.`);
      const bytes = Utilities.base64Decode(base64);
      if (!bytes.length || bytes.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTO_BYTES) {
        throw new Error(`사진 ${index + 1}은 2.5MB 이하로 등록하세요.`);
      }
      return {
        index,
        clientPhotoId,
        bytes,
        fileName: buildHousemanRequestPhotoFileName_(
          String(photo.fileName || `photo_${String(index + 1).padStart(2, '0')}.jpg`),
          orderId
        )
      };
    });

    const missingPhotos = preparedPhotos.filter(photo => !currentClientIds.has(photo.clientPhotoId));
    if (legacyPhotos.length + currentPhotos.length + missingPhotos.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
      throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
    }

    if (!missingPhotos.length) {
      return {
        ok: true,
        orderId,
        photos: currentPhotos,
        savedCount: 0,
        duplicateCount: preparedPhotos.length,
        photoCount: legacyPhotos.length + currentPhotos.length,
        maxPhotos: NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER,
        message: '요청사진이 이미 저장되어 있습니다.',
        photoPerformance: {
          prepareMs: Date.now() - startedAt,
          driveMs: 0,
          metadataWriteMs: 0,
          lockWaitMs: 0,
          elapsedMs: Date.now() - startedAt
        }
      };
    }

    const businessDate = String(orderInfo.data['업무일자'] || '').trim();
    const site = String(orderInfo.data['사업장'] || '').trim();
    const roomNo = String(orderInfo.data['객실번호'] || '').trim();
    const folder = getHousemanRequestPhotoFolder_(businessDate, site, roomNo);
    const prepareMs = Date.now() - startedAt;
    const createdFiles = [];
    const createdPhotos = [];

    try {
      const driveStartedAt = Date.now();
      missingPhotos.forEach(item => {
        const file = folder.createFile(Utilities.newBlob(item.bytes, 'image/jpeg', item.fileName));
        createdFiles.push(file);
        createdPhotos.push({
          clientPhotoId: item.clientPhotoId,
          fileId: file.getId(),
          name: file.getName(),
          mimeType: 'image/jpeg',
          size: item.bytes.length,
          uploadedAt: nowText_(),
          uploadedBy: user.employeeNo
        });
      });
      const driveMs = Date.now() - driveStartedAt;

      // 중요: 이 구간에서도 ScriptLock을 사용하지 않습니다.
      // 운영 오더 상태변경이 사용하는 세부내용JSON과 다른 전용 셀만 수정합니다.
      const metadataWriteStartedAt = Date.now();
      const latestOrderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
      validateHousemanRequestPhotoOrder_(latestOrderInfo, user);
      const latestMetadata = readHousemanRequestPhotoMetadata_(latestOrderInfo.data);
      const mergedPhotos = mergeHousemanRequestPhotoMetadata_(latestMetadata.photos, createdPhotos);
      if (legacyPhotos.length + mergedPhotos.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
        throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
      }
      const metadata = {
        version: NOVA_HOUSEMAN_PHOTO_METADATA_VERSION_,
        photos: mergedPhotos,
        photoAttachedFrom: `${role}_MOBILE`,
        updatedAt: nowText_()
      };
      sheet.getRange(latestOrderInfo.rowNumber, photoColumn).setValue(JSON.stringify(metadata));
      const metadataWriteMs = Date.now() - metadataWriteStartedAt;

      return {
        ok: true,
        orderId,
        photos: mergedPhotos,
        savedCount: createdPhotos.length,
        duplicateCount: preparedPhotos.length - missingPhotos.length,
        photoCount: legacyPhotos.length + mergedPhotos.length,
        maxPhotos: NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER,
        message: `요청사진 ${createdPhotos.length}장을 저장했습니다.`,
        photoPerformance: {
          prepareMs,
          driveMs,
          metadataWriteMs,
          lockWaitMs: 0,
          elapsedMs: Date.now() - startedAt
        }
      };
    } catch (error) {
      // 전용 메타데이터 셀 연결 전 실패한 이번 호출의 파일만 정리합니다.
      createdFiles.forEach(file => {
        try { file.setTrashed(true); } catch (ignore) {}
      });
      throw error;
    }
  });
}

function readHousemanRequestPhotoMetadata_(data) { // (전용 사진 메타데이터 열 안전 파싱)
  let parsed = {};
  try {
    parsed = JSON.parse(String(data && data[NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_] || '{}'));
  } catch (ignore) {
    parsed = {};
  }
  const photos = Array.isArray(parsed)
    ? parsed
    : (Array.isArray(parsed.photos) ? parsed.photos : []);
  return {
    version: Number(parsed.version || NOVA_HOUSEMAN_PHOTO_METADATA_VERSION_),
    photos: photos
      .filter(photo => photo && photo.fileId)
      .slice(0, NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER)
      .map(photo => ({
        clientPhotoId: String(photo.clientPhotoId || '').trim(),
        fileId: String(photo.fileId || '').trim(),
        name: String(photo.name || '').trim(),
        mimeType: String(photo.mimeType || 'image/jpeg').trim(),
        size: Number(photo.size || 0),
        uploadedAt: String(photo.uploadedAt || '').trim(),
        uploadedBy: String(photo.uploadedBy || '').trim()
      }))
  };
}

function mergeHousemanRequestPhotoMetadata_(current, additions) { // (재전송·중복 파일ID 제거)
  const result = [];
  const seenFileIds = new Set();
  const seenClientIds = new Set();
  (Array.isArray(current) ? current : []).concat(Array.isArray(additions) ? additions : []).forEach(photo => {
    if (!photo || !photo.fileId) return;
    const fileId = String(photo.fileId || '').trim();
    const clientPhotoId = String(photo.clientPhotoId || '').trim();
    if (!fileId || seenFileIds.has(fileId) || (clientPhotoId && seenClientIds.has(clientPhotoId))) return;
    seenFileIds.add(fileId);
    if (clientPhotoId) seenClientIds.add(clientPhotoId);
    result.push(photo);
  });
  return result.slice(0, NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER);
}

function setupHousemanRequestPhotoMetadataColumn(token) { // (관리자 1회 준비·운영 중 사진저장에서는 호출하지 않음)
  return measureResponse_('setupHousemanRequestPhotoMetadataColumn', () => {
    requireRole_(token, ['ADMIN']);
    return ensureHousemanRequestPhotoMetadataColumn_();
  });
}

function ensureHousemanRequestPhotoMetadataColumn_() { // (전용 열 1회 생성)
  const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
  const existing = Number(getHeaderMap_(sheet)[NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_] || 0);
  if (existing) return { ok: true, created: false, column: existing, header: NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_ };

  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    // 락 획득 후 다른 실행이 이미 만들었는지 다시 확인합니다.
    NOVA_RUNTIME_CACHE_.headerMaps = {};
    const rechecked = Number(getHeaderMap_(sheet)[NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_] || 0);
    if (rechecked) return { ok: true, created: false, column: rechecked, header: NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_ };
    const column = sheet.getLastColumn() + 1;
    if (column > sheet.getMaxColumns()) sheet.insertColumnAfter(sheet.getMaxColumns());
    sheet.getRange(1, column).setValue(NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_);
    NOVA_RUNTIME_CACHE_.headerMaps = {};
    return { ok: true, created: true, column, header: NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_ };
  } finally {
    lock.releaseLock();
  }
}
