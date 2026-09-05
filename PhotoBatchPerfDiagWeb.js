/** TEMPORARY DIAGNOSTIC ONLY — never merge to main. */
function doPost(e) {
  const mode = String(e && e.parameter && e.parameter.mode || 'batch').trim();
  try {
    let result;
    if (mode === 'prepare') result = diagnoseHousemanPhotoBatchPrepare20260905();
    else if (mode === 'lockProbe') result = diagnosePhotoBatchLockProbe20260905();
    else if (mode === 'cleanup') result = diagnoseHousemanPhotoBatchCleanup20260905();
    else result = diagnoseHousemanPhotoBatchFast20260905();
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
