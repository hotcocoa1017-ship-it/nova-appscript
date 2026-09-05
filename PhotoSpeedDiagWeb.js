/** TEMPORARY DIAGNOSTIC ONLY — never merge to main. */
function doPost(e) {
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
