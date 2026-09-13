/** TEMP: read only the public NOVA Realtime API base from Script Properties. */
function novaRuntimeApiBaseDiagnostic() {
  const apiBase = String(PropertiesService.getScriptProperties().getProperty('NOVA_REALTIME_API_BASE') || '')
    .trim()
    .replace(/\/+$/, '');
  return {
    ok: /^https:\/\//i.test(apiBase),
    apiBase: apiBase
  };
}
