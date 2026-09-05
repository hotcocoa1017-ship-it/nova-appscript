/** TEMPORARY DIAGNOSTIC ONLY — never merge to main. */
function doPost(e) {
  const supplied = String(e && e.parameter && e.parameter.photoSpeedDiag || '').trim();
  const expected = 'c9fd1ad7d1f346e7bd6fb87e0f667fac76698fe7e6e948e69e6b5ca74e758f9a';
  if (supplied !== expected) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, code: 'NOT_FOUND' }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  try {
    const result = diagnoseHousemanPhotoSaveSpeed20260905();
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      ok: false,
      message: error && error.message ? error.message : String(error)
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
