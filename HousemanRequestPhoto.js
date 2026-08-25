/**
 * 룸메이드 하우스맨 요청 사진
 * - 기존 Client.html·10_Mobile.gs·07_Houseman.gs를 수정하지 않고 별도 연결
 * - 기존 업무이력 스키마 변경 없이 HOUSEMAN_ORDER 세부내용JSON에 사진 메타정보만 저장
 */
const NOVA_HOUSEMAN_REQUEST_PHOTO = Object.freeze({
  MAX_PHOTO_BYTES: 2500000,
  MAX_PHOTOS_PER_ORDER: 5,
  ROOT_PROPERTY: 'NOVA_HOUSEMAN_REQUEST_PHOTO_ROOT_ID',
  ROOT_FOLDER_NAME: 'NOVA_하우스맨요청사진'
});

function getMobileHousemanRequestPhotoCapability(token) { // (룸메이드 요청사진 기능 사용 가능 확인)
  return measureResponse_('getMobileHousemanRequestPhotoCapability', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const role = String(auth.user.role || '').trim().toUpperCase();
    return {
      ok: true,
      enabled: role === 'ROOMMAID',
      role,
      maxPhotoBytes: NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTO_BYTES,
      maxPhotos: NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER
    };
  });
}

function uploadMobileHousemanRequestPhoto(token, payload) { // (룸메이드 모바일 하우스맨 요청사진 최대 5장 연결)
  return measureResponse_('uploadMobileHousemanRequestPhoto', () => {
    const auth = verifyNovaToken(token);
    if (!auth.ok) throw new Error('로그인이 필요합니다.');
    const user = auth.user;
    if (String(user.role || '').trim().toUpperCase() !== 'ROOMMAID') throw new Error('룸메이드 요청사진 등록 권한이 없습니다.');

    const safe = payload || {};
    const orderId = String(safe.orderId || '').trim();
    const preferredRowNumber = Number(safe.rowNumber || 0);
    if (!orderId) throw new Error('하우스맨 요청번호가 없습니다.');
    const mimeType = String(safe.mimeType || '').trim().toLowerCase();
    if (mimeType !== 'image/jpeg') throw new Error('JPG 사진만 등록할 수 있습니다.');
    const base64 = String(safe.base64 || '').replace(/^data:[^;]+;base64,/, '').trim();
    if (!base64) throw new Error('사진 데이터가 없습니다.');
    const bytes = Utilities.base64Decode(base64);
    if (!bytes.length || bytes.length > NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTO_BYTES) {
      throw new Error('사진은 2.5MB 이하로 등록하세요.');
    }

    const sheet = getRequiredSheet_(NOVA.SHEETS.HISTORY);
    const initialOrderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
    const initialDetail = validateHousemanRequestPhotoOrder_(initialOrderInfo, user); // (파일 생성 전 소유권·출처 검증)
    const initialPhotos = Array.isArray(initialDetail.photos)
      ? initialDetail.photos.filter(photo => photo && photo.fileId)
      : [];
    if (initialPhotos.length >= NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
      throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
    }

    const businessDate = String(initialOrderInfo.data['업무일자'] || '').trim();
    const site = String(initialOrderInfo.data['사업장'] || '').trim();
    const roomNo = String(initialOrderInfo.data['객실번호'] || '').trim();
    const folder = getHousemanRequestPhotoFolder_(businessDate, site, roomNo);
    const fileName = buildHousemanRequestPhotoFileName_(safe.fileName, orderId);
    let file = null;
    let savedPhotoCount = 0;

    try {
      file = folder.createFile(Utilities.newBlob(bytes, 'image/jpeg', fileName));
      const uploadedAt = nowText_();
      const photo = {
        fileId: file.getId(),
        name: file.getName(),
        mimeType: 'image/jpeg',
        size: bytes.length,
        uploadedAt,
        uploadedBy: user.employeeNo
      };

      const writeLock = acquireWriteLock_();
      try {
        const latestOrderInfo = findHousemanOrderRow_(sheet, orderId, preferredRowNumber);
        const latestDetail = validateHousemanRequestPhotoOrder_(latestOrderInfo, user); // (동시 업로드 전 최종 재검증)
        const latestPhotos = Array.isArray(latestDetail.photos)
          ? latestDetail.photos.filter(item => item && item.fileId)
          : [];
        if (latestPhotos.length >= NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER) {
          throw new Error(`요청사진은 최대 ${NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER}장까지 등록할 수 있습니다.`);
        }
        latestDetail.photos = latestPhotos.concat([photo]);
        savedPhotoCount = latestDetail.photos.length;
        latestDetail.photoAttachedFrom = 'ROOMMAID_MOBILE';
        updateRowByHeaders_(sheet, latestOrderInfo.rowNumber, {
          '세부내용JSON': JSON.stringify(latestDetail)
        }); // (오더 상태·수정일시·변경버전은 변경하지 않음)
      } finally {
        writeLock.releaseLock();
      }

      return {
        ok: true,
        orderId,
        photo,
        photoCount: savedPhotoCount,
        maxPhotos: NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER,
        message: '요청사진을 등록했습니다.'
      };
    } catch (error) {
      if (file) {
        try { file.setTrashed(true); } catch (ignore) {}
      }
      throw error;
    }
  });
}

function validateHousemanRequestPhotoOrder_(orderInfo, user) { // (사진 연결 대상 하우스맨 요청 검증)
  if (!orderInfo || !orderInfo.data) throw new Error('하우스맨 요청을 찾을 수 없습니다.');
  const data = orderInfo.data;
  if (String(data['기록구분'] || '').trim() !== NOVA.RECORD_TYPES.HOUSEMAN_ORDER) throw new Error('하우스맨 요청 자료가 아닙니다.');
  if (String(data['등록사번'] || '').trim() !== String(user.employeeNo || '').trim()) throw new Error('본인이 등록한 요청에만 사진을 추가할 수 있습니다.');
  if (String(data['삭제여부'] || 'N').trim().toUpperCase() === 'Y') throw new Error('삭제된 요청에는 사진을 추가할 수 없습니다.');

  let detail = {};
  try { detail = JSON.parse(String(data['세부내용JSON'] || '{}')); } catch (error) { detail = {}; }
  if (String(detail.createdFrom || '').trim().toUpperCase() !== 'MOBILE'
      || String(detail.requestSource || '').trim().toUpperCase() !== 'ROOMMAID') {
    throw new Error('룸메이드 모바일 요청에만 사진을 추가할 수 있습니다.');
  }
  return detail;
}

function buildHousemanRequestPhotoFileName_(sourceName, orderId) { // (요청사진 파일명 안전 정리)
  const raw = String(sourceName || 'houseman-request.jpg')
    .replace(/[\\/:*?"<>|#%{}~]/g, '_')
    .slice(0, 80) || 'houseman-request.jpg';
  const baseName = raw.replace(/\.[^.]+$/, '') || 'houseman-request';
  const time = Utilities.formatDate(new Date(), NOVA.TIMEZONE, 'HHmmss');
  return `${time}_${orderId}_${baseName}.jpg`;
}

function getHousemanRequestPhotoFolder_(businessDate, site, roomNo) { // (요청사진 날짜·사업장·객실 폴더)
  const props = PropertiesService.getScriptProperties();
  let root = null;
  const rootId = props.getProperty(NOVA_HOUSEMAN_REQUEST_PHOTO.ROOT_PROPERTY);
  if (rootId) {
    try { root = DriveApp.getFolderById(rootId); } catch (error) { root = null; }
  }
  if (!root) {
    root = DriveApp.createFolder(NOVA_HOUSEMAN_REQUEST_PHOTO.ROOT_FOLDER_NAME);
    props.setProperty(NOVA_HOUSEMAN_REQUEST_PHOTO.ROOT_PROPERTY, root.getId());
  }
  const dateFolder = getOrCreateHousemanRequestPhotoFolder_(root, businessDate || businessDateText_());
  const siteFolder = getOrCreateHousemanRequestPhotoFolder_(dateFolder, sanitizeHousemanRequestPhotoFolderName_(site || '미지정'));
  return getOrCreateHousemanRequestPhotoFolder_(siteFolder, sanitizeHousemanRequestPhotoFolderName_(roomNo || '미지정'));
}

function getOrCreateHousemanRequestPhotoFolder_(parent, name) { // (요청사진 하위폴더 조회·생성)
  const folders = parent.getFoldersByName(name);
  return folders.hasNext() ? folders.next() : parent.createFolder(name);
}

function sanitizeHousemanRequestPhotoFolderName_(value) { // (Drive 폴더명 안전 정리)
  return String(value || '미지정').trim().replace(/[\\/:*?"<>|]/g, '_').slice(0, 80) || '미지정';
}
