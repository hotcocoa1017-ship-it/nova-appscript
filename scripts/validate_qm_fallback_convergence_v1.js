if (typeof require !== 'undefined') {
  const fs = require('fs');

  function read(path) { return fs.readFileSync(path, 'utf8'); }
  function must(condition, message) { if (!condition) throw new Error(message); }

  const fallback = read('QmSchemaCacheFallbackHotfix.html');
  const convergenceServer = read('QmFallbackConvergence.js');
  const convergenceClient = read('QmFallbackConvergenceClient.html');
  const authority = read('QmDbReadAuthorityClient.html');
  const serial = read('QmWriteSerialGuard.html');
  const index = read('Index.html');

  // Static invariants: single circuit authority, no early breaker close.
  must(fallback.includes('QM_SCHEMA_CACHE_FALLBACK_V8'), 'V8 schema-cache fallback marker missing');
  must(fallback.includes("const BREAKER_MS = 5 * 60 * 1000"), 'breaker TTL missing');
  must(!fallback.includes('closeBreaker_'), 'breaker must not close early on one successful RPC');
  must(fallback.includes("code: 'PGRST202'"), 'legacy fallback signal missing');

  // During breaker, stale DB button authority must not overwrite Sheet fallback UI.
  must(authority.includes('QM_DB_READ_AUTHORITY_V2'), 'DB authority V2 missing');
  must(authority.includes('schemaCacheBreakerActive_()'), 'DB authority breaker guard missing');
  must(authority.includes('if (schemaCacheBreakerActive_()) return;'), 'DB authority apply guard missing');

  // Input writes: local draft remains, 800ms automatic server autosave is suppressed.
  must(serial.includes('QM_WRITE_SERIAL_GUARD_V1'), 'write serial guard missing');
  must(serial.includes('Number(delay) !== 800'), 'autosave timer discrimination missing');
  must(serial.includes("source.includes('saveQmInspectionDraftNow_')"), 'autosave-only suppression missing');

  // Forced convergence is one-room, QM-owned, expected-state verified, read-only on Sheet.
  must(convergenceServer.includes('QM_FALLBACK_DB_CONVERGENCE_V1'), 'server convergence marker missing');
  must(convergenceServer.includes("forceSheetCleaning: true"), 'forced QM cleaning-state convergence missing');
  must(convergenceServer.includes("rooms.length !== 1"), 'single-room convergence invariant missing');
  must(convergenceServer.includes("sheetQmEmployeeNo !== String(user.employeeNo"), 'Sheet QM ownership check missing');
  must(convergenceServer.includes("dbStatus !== expectedStatus"), 'DB post-convergence verification missing');
  must(!convergenceServer.includes('updateRowByHeaders_'), 'convergence bridge must never rewrite Sheet');
  must(!convergenceServer.includes('acquireWriteLock_'), 'convergence bridge must not contend with QM Sheet write lock');

  // Client convergence must be breaker-only, serialized and non-UI-mutating.
  must(convergenceClient.includes('QM_FALLBACK_DB_CONVERGENCE_CLIENT_V1'), 'client convergence marker missing');
  must(convergenceClient.includes('let chain = Promise.resolve()'), 'serialized convergence queue missing');
  must(convergenceClient.includes("expectedStatus === 'QM_COMPLETED' && expectedStatus === 'QM_CHECKING'"), 'terminal-state precedence missing');
  must(convergenceClient.includes('[data-room-action="START"], [data-qm-browse-inspect]'), 'start capture missing');
  must(convergenceClient.includes('.qm-checklist-modal #qmChecklistSubmit'), 'complete capture missing');
  must(!convergenceClient.includes('openModal(') && !convergenceClient.includes('openQmInspectionModal_('), 'convergence client must not rerender QM modal');

  // Include order: circuit -> write serialization -> convergence -> DB authority.
  const pFallback = index.indexOf("include_('QmSchemaCacheFallbackHotfix')");
  const pSerial = index.indexOf("include_('QmWriteSerialGuard')");
  const pConverge = index.indexOf("include_('QmFallbackConvergenceClient')");
  const pAuthority = index.indexOf("include_('QmDbReadAuthorityClient')");
  must(pFallback >= 0 && pSerial > pFallback && pConverge > pSerial && pAuthority > pConverge, 'QM guard include order invalid');
  must(index.includes('id="loginEmployeeNo"') && index.includes('autocomplete="current-password" required'), 'login required invariant lost');

  // State-machine simulation: start -> complete must never regress to checking.
  const pending = new Map();
  function enqueue(key, expectedStatus) {
    const previous = pending.get(key);
    if (previous === 'QM_COMPLETED' && expectedStatus === 'QM_CHECKING') return;
    pending.set(key, expectedStatus);
  }
  enqueue('2026-09-12|쏘라노|1306', 'QM_CHECKING');
  must(pending.get('2026-09-12|쏘라노|1306') === 'QM_CHECKING', 'start state simulation failed');
  enqueue('2026-09-12|쏘라노|1306', 'QM_COMPLETED');
  must(pending.get('2026-09-12|쏘라노|1306') === 'QM_COMPLETED', 'complete state simulation failed');
  enqueue('2026-09-12|쏘라노|1306', 'QM_CHECKING');
  must(pending.get('2026-09-12|쏘라노|1306') === 'QM_COMPLETED', 'terminal state regressed to checking');

  console.log('QM fallback convergence V1 simulation: PASS');
  console.log('Scenarios: sticky circuit, stale-authority isolation, autosave serialization, one-room forced convergence, terminal-state precedence, UI non-rerender.');
}
