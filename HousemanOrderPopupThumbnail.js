/**
 * HOUSEMAN_POPUP_SERVER_THUMBNAIL_V3
 * 하우스맨 오더 팝업 자동표시 전용 썸네일 조회.
 * - Supabase Storage 사진: Edge Function이 256px 변환 signed URL만 발급합니다.
 * - Legacy Drive 사진: Drive가 생성한 thumbnailLink의 작은 이미지만 가져옵니다.
 * - 기존 원본 사진 조회 API(getHousemanRequestPhoto)는 변경하지 않습니다.
 */
const NOVA_HOUSEMAN_POPUP_THUMBNAIL = Object.freeze({
  EDGE_SLUG: 'nova-houseman-photo-v1',
  MAX_THUMB_BYTES: 768 * 1024,
  DRIVE_FIELDS: 'id,name,mimeType,size,thumbnailLink'
});

function getHousemanOrderPopupThumbnail(token, payload) {
  return measureResponse_('getHousemanOrderPopupThumbnail', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);
    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const fileId = String(safe.fileId || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    if (!orderId || !fileId) throw new Error('썸네일을 확인할 오더와 파일정보가 없습니다.');

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
    try { detail = JSON.parse(String(orderInfo.data['세부내용JSON'] || '{}')); } catch (ignore) { detail = {}; }
    const photos = getHousemanRequestPhotosForDisplay_(orderInfo.data, detail);
    const photo = photos.find(item => String(item && item.fileId || '').trim() === fileId);
    if (!photo) throw new Error('해당 오더에 연결된 사진을 찾을 수 없습니다.');

    if (/^sb:[0-9a-f-]{36}$/i.test(fileId)) {
      return getHousemanOrderPopupStorageThumbnail_(token, orderId, orderInfo, photo);
    }
    return getHousemanOrderPopupDriveThumbnail_(orderId, orderInfo, photo);
  });
}

function getHousemanOrderPopupStorageThumbnail_(token, orderId, orderInfo, photo) {
  const fileId = String(photo && photo.fileId || '').trim();
  const photoId = fileId.replace(/^sb:/i, '');
  if (!/^[0-9a-f-]{36}$/i.test(photoId)) throw new Error('사진 식별값이 올바르지 않습니다.');

  const realtime = getHousemanPhotoRealtimeAuth_(token);
  const edgeUrl = `${String(realtime.supabaseUrl || '').replace(/\/+$/, '')}/functions/v1/${NOVA_HOUSEMAN_POPUP_THUMBNAIL.EDGE_SLUG}`;
  const edgeResponse = UrlFetchApp.fetch(edgeUrl, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': `Bearer ${realtime.token}`,
      'apikey': String(realtime.publishableKey || '')
    },
    payload: JSON.stringify({ action: 'thumbnail', orderId, photoId }),
    muteHttpExceptions: true
  });
  let edgeData = {};
  try { edgeData = JSON.parse(edgeResponse.getContentText() || '{}'); } catch (ignore) { edgeData = {}; }
  if (edgeResponse.getResponseCode() < 200 || edgeResponse.getResponseCode() >= 300 || !edgeData.ok || !edgeData.signedUrl) {
    throw new Error(String(edgeData.message || '썸네일 조회 URL을 만들지 못했습니다.'));
  }

  return {
    ok: true,
    orderId,
    rowNumber: Number(orderInfo && orderInfo.rowNumber || 0),
    photo: {
      fileId,
      name: String(photo && photo.name || 'houseman-request.jpg'),
      mimeType: 'image/jpeg',
      size: Math.max(0, Number(edgeData.photo && edgeData.photo.size || photo && photo.size || 0)),
      uploadedAt: String(photo && photo.uploadedAt || '')
    },
    signedUrl: String(edgeData.signedUrl),
    expiresIn: Math.max(1, Number(edgeData.expiresIn || 300)),
    thumbnail: true,
    width: Math.max(1, Number(edgeData.width || 256)),
    source: 'SUPABASE_TRANSFORM'
  };
}

function getHousemanOrderPopupDriveThumbnail_(orderId, orderInfo, photo) {
  const fileId = String(photo && photo.fileId || '').trim();
  if (!fileId) throw new Error('사진 식별값이 없습니다.');
  const oauthToken = ScriptApp.getOAuthToken();
  const metadataUrl = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}?fields=${encodeURIComponent(NOVA_HOUSEMAN_POPUP_THUMBNAIL.DRIVE_FIELDS)}`;
  const metadataResponse = UrlFetchApp.fetch(metadataUrl, {
    method: 'get',
    headers: { 'Authorization': `Bearer ${oauthToken}` },
    muteHttpExceptions: true
  });
  let metadata = {};
  try { metadata = JSON.parse(metadataResponse.getContentText() || '{}'); } catch (ignore) { metadata = {}; }
  if (metadataResponse.getResponseCode() < 200 || metadataResponse.getResponseCode() >= 300) {
    throw new Error('Drive 사진 썸네일 정보를 확인하지 못했습니다.');
  }
  const thumbnailLink = String(metadata.thumbnailLink || '').trim();
  if (!thumbnailLink) throw new Error('이 사진은 Drive 썸네일을 제공하지 않습니다.');

  const thumbnailResponse = UrlFetchApp.fetch(thumbnailLink, {
    method: 'get',
    headers: { 'Authorization': `Bearer ${oauthToken}` },
    muteHttpExceptions: true,
    followRedirects: true
  });
  const status = thumbnailResponse.getResponseCode();
  if (status < 200 || status >= 300) throw new Error('Drive 썸네일을 불러오지 못했습니다.');
  const blob = thumbnailResponse.getBlob();
  const bytes = blob.getBytes();
  if (!bytes.length) throw new Error('Drive 썸네일이 비어 있습니다.');
  if (bytes.length > NOVA_HOUSEMAN_POPUP_THUMBNAIL.MAX_THUMB_BYTES) {
    throw new Error('Drive 썸네일 용량이 예상보다 큽니다.');
  }

  return {
    ok: true,
    orderId,
    rowNumber: Number(orderInfo && orderInfo.rowNumber || 0),
    photo: {
      fileId,
      name: String(metadata.name || photo && photo.name || 'houseman-request.jpg'),
      mimeType: String(blob.getContentType() || 'image/jpeg'),
      size: bytes.length,
      uploadedAt: String(photo && photo.uploadedAt || '')
    },
    base64: Utilities.base64Encode(bytes),
    thumbnail: true,
    source: 'DRIVE_THUMBNAIL'
  };
}
