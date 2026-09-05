/** HOUSEMAN_PHOTO_BATCH_FAST_V2 · legacy 세부내용JSON + 전용 요청사진JSON 통합조회 */
function getHousemanRequestPhotosForDisplay_(data, detail) {
  const legacy = detail && Array.isArray(detail.photos)
    ? detail.photos.filter(photo => photo && photo.fileId)
    : [];
  const dedicated = readHousemanRequestPhotoMetadata_(data).photos;
  const merged = [];
  const seen = new Set();
  legacy.concat(dedicated).forEach(photo => {
    const fileId = String(photo && photo.fileId || '').trim();
    if (!fileId || seen.has(fileId)) return;
    seen.add(fileId);
    merged.push({
      clientPhotoId: String(photo.clientPhotoId || '').trim(),
      fileId,
      name: String(photo.name || '').trim(),
      mimeType: String(photo.mimeType || 'image/jpeg').trim(),
      size: Number(photo.size || 0),
      uploadedAt: String(photo.uploadedAt || '').trim(),
      uploadedBy: String(photo.uploadedBy || '').trim()
    });
  });
  return merged.slice(0, NOVA_HOUSEMAN_REQUEST_PHOTO.MAX_PHOTOS_PER_ORDER);
}
