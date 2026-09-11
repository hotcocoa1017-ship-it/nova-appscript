/**
 * HOUSEMAN_POPUP_CREATOR_PHOTO_V1
 * 하우스맨 오더 상세 팝업의 등록자·요청사진 표시용 읽기 전용 보조 API.
 * 기존 오더 조회/처리 경로와 분리하여 팝업 오픈을 차단하지 않습니다.
 */
function getHousemanOrderPopupExtras(token, payload) { // (하우스맨 팝업 등록자·사진 메타 조회 전용)
  return measureResponse_('getHousemanOrderPopupExtras', () => {
    requireRole_(token, ['ADMIN', 'ORDER']);

    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    if (!orderId) throw new Error('하우스맨 오더 번호가 없습니다.');

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const orderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
    if (!orderInfo || !orderInfo.data) throw new Error('하우스맨 오더를 찾을 수 없습니다.');

    const data = orderInfo.data;
    if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ORDER) {
      throw new Error('하우스맨 오더 자료가 아닙니다.');
    }
    if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') {
      throw new Error('삭제된 하우스맨 오더입니다.');
    }

    let detail = {};
    try {
      detail = JSON.parse(String(data['세부내용JSON'] || '{}'));
    } catch (ignore) {
      detail = {};
    }

    const registeredByEmployeeNo = String(data['등록사번'] || '').trim();
    const usersByEmployeeNo = getUserIndex_().byEmployeeNo || {};
    const registeredUser = registeredByEmployeeNo
      ? usersByEmployeeNo[registeredByEmployeeNo]
      : null;
    const registeredByName = String(
      registeredUser && registeredUser.name || registeredByEmployeeNo || '-'
    ).trim() || '-';

    const photos = getHousemanRequestPhotosForDisplay_(data, detail).map(photo => ({
      fileId: String(photo.fileId || '').trim(),
      name: String(photo.name || '').trim(),
      mimeType: String(photo.mimeType || 'image/jpeg').trim(),
      size: Math.max(0, Number(photo.size || 0)),
      uploadedAt: String(photo.uploadedAt || '').trim(),
      uploadedBy: String(photo.uploadedBy || '').trim()
    })).filter(photo => photo.fileId);

    return {
      ok: true,
      orderId,
      rowNumber: Number(orderInfo.rowNumber || 0),
      registeredByEmployeeNo,
      registeredByName,
      photoCount: photos.length,
      photos
    };
  });
}
