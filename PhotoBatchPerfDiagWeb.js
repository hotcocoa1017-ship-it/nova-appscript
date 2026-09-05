/** TEMPORARY DIAGNOSTIC ONLY — never merge to main. */
function doPost(e) {
  const mode = String(e && e.parameter && e.parameter.mode || 'batch').trim();
  try {
    const result = mode === 'lockProbe'
      ? diagnosePhotoBatchLockProbe20260905()
      : diagnoseHousemanPhotoBatchFast20260905();
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      ok: false,
      message: error && error.message ? error.message : String(error),
      code: error && error.code ? error.code : ''
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
