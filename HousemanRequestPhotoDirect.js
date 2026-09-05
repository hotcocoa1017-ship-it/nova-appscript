/**
 * HOUSEMAN_PHOTO_DIRECT_STORAGE_V1
 * - 사진 바이너리는 Apps Script/Drive를 통과하지 않습니다.
 * - 브라우저가 Supabase Private Storage signed upload로 직접 전송합니다.
 * - Apps Script는 기존 월별조회 호환을 위한 가벼운 참조 메타데이터만 후행 기록합니다.
 */
const NOVA_HOUSEMAN_PHOTO_DIRECT = Object.freeze({
  EDGE_SLUG: 'nova-houseman-photo-v1',
  STORAGE_FILE_PREFIX: 'sb:',
  MAX_PHOTOS: 5,
  MAX_DOWNLOAD_BYTES: 5 * 1024 * 1024
});

function linkMobileHousemanStoragePhotoMetadata(token, payload) { // (Storage 사진 참조만 후행 연결 · Drive/ScriptLock 없음)
  return measureResponse_('linkMobileHousemanStoragePhotoMetadata', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const user = auth.user;
    const role = String(user.role || '').trim().toUpperCase();
    if (!['ROOMMAID', 'QM', 'PUBLIC'].includes(role)) throw new Error('하우스맨 요청사진 등록 권한이 없습니다.');

    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    const sourcePhotos = Array.isArray(safe.photos) ? safe.photos : [];
    if (!orderId) throw new Error('하우스맨 요청번호가 없습니다.');
    if (!sourcePhotos.length || sourcePhotos.length > NOVA_HOUSEMAN_PHOTO_DIRECT.MAX_PHOTOS) {
      throw new Error('연결할 요청사진 정보가 올바르지 않습니다.');
    }

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const photoColumn = Number(getHeaderMap_(sheet)[NOVA_HOUSEMAN_PHOTO_METADATA_HEADER_] || 0);
    if (!photoColumn) throw new Error('요청사진 저장영역이 준비되지 않았습니다.');

    const orderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
    validateHousemanRequestPhotoOrder_(orderInfo, user);

    const normalized = sourcePhotos.map((raw, index) => {
      const photo = raw || {};
      const rawFileId = String(photo.fileId || '').trim();
      const photoId = String(photo.photoId || rawFileId.replace(/^sb:/i, '')).trim();
      if (!/^[0-9a-f-]{36}$/i.test(photoId)) throw new Error(`사진 ${index + 1} 식별값이 올바르지 않습니다.`);
      const fileId = `${NOVA_HOUSEMAN_PHOTO_DIRECT.STORAGE_FILE_PREFIX}${photoId}`;
      return {
        clientPhotoId: String(photo.clientPhotoId || '').trim().slice(0, 120),
        fileId,
        name: String(photo.name || `houseman_${index + 1}.jpg`).trim().slice(0, 120),
        mimeType: 'image/jpeg',
        size: Math.max(0, Number(photo.size || 0)),
        uploadedAt: String(photo.uploadedAt || nowText_()).trim(),
        uploadedBy: String(photo.uploadedBy || user.employeeNo).trim()
      };
    });

    const currentMetadata = readHousemanRequestPhotoMetadata_(orderInfo.data);
    const mergedPhotos = mergeHousemanRequestPhotoMetadata_(currentMetadata.photos, normalized);
    let detail = {};
    try { detail = JSON.parse(String(orderInfo.data['세부내용JSON'] || '{}')); } catch (ignore) { detail = {}; }
    const legacyCount = Array.isArray(detail.photos) ? detail.photos.filter(photo => photo && photo.fileId).length : 0;
    if (legacyCount + mergedPhotos.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
      throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
    }

    // 중요: 운영 상태변경이 사용하는 세부내용JSON/수정일시/변경버전은 건드리지 않습니다.
    // 사진 전용 열 1셀만 기록하며 ScriptLock도 사용하지 않습니다.
    sheet.getRange(orderInfo.rowNumber, photoColumn).setValue(JSON.stringify({
      version: NOVA_HOUSEMAN_PHOTO_METADATA_VERSION_,
      photos: mergedPhotos,
      photoAttachedFrom: `${role}_MOBILE_STORAGE`,
      updatedAt: nowText_()
    }));

    return {
      ok: true,
      orderId,
      rowNumber: Number(orderInfo.rowNumber || 0),
      photoCount: legacyCount + mergedPhotos.length,
      linkedCount: normalized.length
    };
  });
}

function getHousemanRequestPhotoFromStorage_(token, orderId, orderInfo, photo) { // (ADMIN/ORDER Storage 사진 조회 호환)
  requireRole_(token, ['ADMIN', 'ORDER']);
  const fileId = String(photo && photo.fileId || '').trim();
  const photoId = fileId.replace(/^sb:/i, '');
  if (!/^[0-9a-f-]{36}$/i.test(photoId)) throw new Error('사진 식별값이 올바르지 않습니다.');

  const realtime = getHousemanPhotoRealtimeAuth_(token);
  const edgeUrl = `${String(realtime.supabaseUrl || '').replace(/\/+$/, '')}/functions/v1/${NOVA_HOUSEMAN_PHOTO_DIRECT.EDGE_SLUG}`;
  const edgeResponse = UrlFetchApp.fetch(edgeUrl, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': `Bearer ${realtime.token}`,
      'apikey': String(realtime.publishableKey || '')
    },
    payload: JSON.stringify({ action: 'view', orderId, photoId }),
    muteHttpExceptions: true
  });
  let edgeData = {};
  try { edgeData = JSON.parse(edgeResponse.getContentText() || '{}'); } catch (ignore) { edgeData = {}; }
  if (edgeResponse.getResponseCode() < 200 || edgeResponse.getResponseCode() >= 300 || !edgeData.ok || !edgeData.signedUrl) {
    throw new Error(String(edgeData.message || '사진 조회 URL을 만들지 못했습니다.'));
  }

  const imageResponse = UrlFetchApp.fetch(String(edgeData.signedUrl), { muteHttpExceptions: true });
  const status = imageResponse.getResponseCode();
  if (status < 200 || status >= 300) throw new Error('사진 파일을 불러오지 못했습니다.');
  const bytes = imageResponse.getBlob().getBytes();
  if (!bytes.length) throw new Error('사진 파일이 비어 있습니다.');
  if (bytes.length > NOVA_HOUSEMAN_PHOTO_DIRECT.MAX_DOWNLOAD_BYTES) throw new Error('사진 파일 용량이 너무 큽니다.');

  return {
    ok: true,
    orderId,
    rowNumber: Number(orderInfo && orderInfo.rowNumber || 0),
    photo: {
      fileId,
      name: String(photo && photo.name || 'houseman-request.jpg'),
      mimeType: 'image/jpeg',
      size: bytes.length,
      uploadedAt: String(photo && photo.uploadedAt || '')
    },
    base64: Utilities.base64Encode(bytes),
    storage: 'SUPABASE'
  };
}

function getHousemanPhotoRealtimeAuth_(token) { // (기존 Cloud Run Realtime JWT 발급 경로 재사용)
  const apiBase = String(PropertiesService.getScriptProperties().getProperty('NOVA_REALTIME_API_BASE') || '')
    .trim().replace(/\/+$/, '');
  if (!apiBase) throw new Error('Realtime 사진 연결정보가 없습니다.');
  const response = UrlFetchApp.fetch(`${apiBase}/v1/auth/realtime-token`, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'Authorization': `Bearer ${token}` },
    payload: '{}',
    muteHttpExceptions: true
  });
  let data = {};
  try { data = JSON.parse(response.getContentText() || '{}'); } catch (ignore) { data = {}; }
  if (response.getResponseCode() < 200 || response.getResponseCode() >= 300 || !data.ok || !data.token || !data.supabaseUrl || !data.publishableKey) {
    throw new Error(String(data.message || '사진 조회 인증을 만들지 못했습니다.'));
  }
  return data;
}
