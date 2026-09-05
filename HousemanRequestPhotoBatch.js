/**
 * HOUSEMAN_PHOTO_BATCH_FAST_V1
 * 하우스맨 요청/습득물 사진을 한 번에 저장하여 운영 저장경로와의 경합을 최소화합니다.
 * - 오더 등록 경로와 분리된 후행 저장 전용
 * - 권한/오더/폴더 조회 1회
 * - Drive 파일은 ScriptLock 밖에서 생성
 * - HISTORY 세부내용JSON 연결은 짧은 ScriptLock 1회만 사용
 */

function uploadMobileHousemanRequestPhotos(token, payload) { // (최대 5장 일괄 후행 저장)
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

    // 파일 생성 전에 전체 payload를 먼저 검증합니다. 한 장이라도 비정상이면 Drive를 건드리지 않습니다.
    const preparedPhotos = sourcePhotos.map((source, index) => {
      const photo = source || {};
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
        bytes,
        fileName: buildHousemanRequestPhotoFileName_(
          String(photo.fileName || `photo_${String(index + 1).padStart(2, '0')}.jpg`),
          orderId
        )
      };
    });

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const initialOrderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
    const initialDetail = validateHousemanRequestPhotoOrder_(initialOrderInfo, user);
    const initialPhotos = Array.isArray(initialDetail.photos)
      ? initialDetail.photos.filter(photo => photo && photo.fileId)
      : [];
    if (initialPhotos.length + preparedPhotos.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
      throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
    }

    const businessDate = String(initialOrderInfo.data['업무일자'] || '').trim();
    const site = String(initialOrderInfo.data['사업장'] || '').trim();
    const roomNo = String(initialOrderInfo.data['객실번호'] || '').trim();
    const folder = getHousemanRequestPhotoFolder_(businessDate, site, roomNo);
    const prepareMs = Date.now() - startedAt;
    const createdFiles = [];
    const createdPhotos = [];
    let lockWaitMs = 0;
    let linkMs = 0;

    try {
      const driveStartedAt = Date.now();
      preparedPhotos.forEach(item => {
        const file = folder.createFile(Utilities.newBlob(item.bytes, 'image/jpeg', item.fileName));
        createdFiles.push(file);
        createdPhotos.push({
          fileId: file.getId(),
          name: file.getName(),
          mimeType: 'image/jpeg',
          size: item.bytes.length,
          uploadedAt: nowText_(),
          uploadedBy: user.employeeNo
        });
      });
      const driveMs = Date.now() - driveStartedAt;

      // 운영 상태변경/오더 저장을 사진 때문에 기다리게 하지 않도록 락은 마지막 JSON 연결 순간에만 짧게 사용합니다.
      const lockResult = acquireHousemanPhotoLinkLock_();
      lockWaitMs = lockResult.waitMs;
      const writeLock = lockResult.lock;
      try {
        const linkStartedAt = Date.now();
        const latestOrderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
        const latestDetail = validateHousemanRequestPhotoOrder_(latestOrderInfo, user);
        const latestPhotos = Array.isArray(latestDetail.photos)
          ? latestDetail.photos.filter(item => item && item.fileId)
          : [];
        if (latestPhotos.length + createdPhotos.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
          throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
        }
        latestDetail.photos = latestPhotos.concat(createdPhotos);
        latestDetail.photoAttachedFrom = `${role}_MOBILE`;
        updateRowByHeaders_(sheet, latestOrderInfo.rowNumber, {
          '세부내용JSON': JSON.stringify(latestDetail)
        }); // 오더 상태·수정일시·변경버전은 변경하지 않음
        linkMs = Date.now() - linkStartedAt;
      } finally {
        writeLock.releaseLock();
      }

      return {
        ok: true,
        orderId,
        photos: createdPhotos,
        savedCount: createdPhotos.length,
        photoCount: initialPhotos.length + createdPhotos.length,
        maxPhotos: NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER,
        message: `요청사진 ${createdPhotos.length}장을 저장했습니다.`,
        photoPerformance: {
          prepareMs,
          driveMs,
          lockWaitMs,
          linkMs,
          elapsedMs: Date.now() - startedAt
        }
      };
    } catch (error) {
      // HISTORY 연결이 실패한 경우 이번 호출에서 만든 파일만 정리하여 고아파일을 남기지 않습니다.
      createdFiles.forEach(file => {
        try { file.setTrashed(true); } catch (ignore) {}
      });
      throw error;
    }
  });
}

function acquireHousemanPhotoLinkLock_() { // (사진은 운영 저장보다 우선하지 않는 짧은 후행락)
  const lock = LockService.getScriptLock();
  const startedAt = Date.now();
  for (let attempt = 0; attempt < 6; attempt += 1) {
    if (lock.tryLock(250)) {
      return { lock, waitMs: Date.now() - startedAt };
    }
    if (attempt < 5) Utilities.sleep(100 + attempt * 40);
  }
  const error = new Error('요청은 등록되었습니다. 사진 저장은 잠시 후 다시 시도해 주세요.');
  error.code = 'BUSY_RETRY';
  throw error;
}
