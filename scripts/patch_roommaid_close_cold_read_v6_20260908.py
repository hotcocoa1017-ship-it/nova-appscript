from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


repo = Path(__file__).resolve().parents[1]

# 1) User index: cache the canonical user list in bounded chunks, then rebuild indexes in memory.
#    This preserves the existing getUserIndex_() contract while avoiding a full user-sheet read
#    on most new Apps Script executions.
repository_path = repo / "02_Repository.js"
repository = repository_path.read_text(encoding="utf-8")
start = repository.index("function getUserIndex_() { // (사용자계정 인덱스 조회)")
end = repository.index("function rowToUser_", start)
new_user_index = r'''const NOVA_USER_INDEX_CACHE_META_V3_ = 'NOVA_USER_INDEX_V3_META'; // USER_INDEX_CHUNK_CACHE_V3
const NOVA_USER_INDEX_CACHE_CHUNK_PREFIX_V3_ = 'NOVA_USER_INDEX_V3_CHUNK_';
const NOVA_USER_INDEX_CACHE_CHUNK_SIZE_V3_ = 25;

function getUserIndex_() { // (사용자계정 인덱스 조회 · USER_INDEX_CHUNK_CACHE_V3)
  if (NOVA_RUNTIME_CACHE_.userIndex) return NOVA_RUNTIME_CACHE_.userIndex; // NOVA_USER_INDEX_RUNTIME_CACHE_V1
  const cache = CacheService.getScriptCache();

  const cachedUsers = readCachedUserListV3_(cache);
  if (cachedUsers) {
    const index = buildUserIndexFromListV3_(cachedUsers);
    NOVA_RUNTIME_CACHE_.userIndex = index;
    return index;
  }

  // 배포 전 단일 캐시가 아직 살아 있으면 1회 호환 사용합니다.
  const legacyCached = cache.get('NOVA_USER_INDEX_V2');
  if (legacyCached) {
    try {
      const parsed = JSON.parse(legacyCached);
      if (parsed && parsed.byEmployeeNo && parsed.byName && parsed.active) {
        NOVA_RUNTIME_CACHE_.userIndex = parsed;
        cacheUserListV3_(cache, Object.values(parsed.byEmployeeNo || {}));
        return parsed;
      }
    } catch (error) {}
  }

  const sheet = getRequiredSheet_(NOVA.SHEETS.USERS);
  const headerMap = getHeaderMap_(sheet);
  const lastRow = sheet.getLastRow();
  const users = [];

  if (lastRow >= 2) {
    const requiredHeaders = [
      '사번', '이름', '직무', '채용구분', '권한', '사용여부', '텔레그램ID', '텔레그램알림',
      '연락처', '기본사업장', '기본담당동', '비고', '수정일시', '텔레그램연결키',
      '텔레그램연결링크', '텔레그램연결상태', '텔레그램연결일시'
    ];
    const projectedLastColumn = requiredHeaders.reduce(
      (max, header) => Math.max(max, Number(headerMap[header] || 0)), 0
    ) || sheet.getLastColumn();
    const values = sheet.getRange(2, 1, lastRow - 1, projectedLastColumn).getDisplayValues();
    values.forEach((row, offset) => {
      const user = rowToUser_(row, offset + 2, headerMap);
      if (user.employeeNo && user.name) users.push(user);
    });
  }

  const index = buildUserIndexFromListV3_(users);
  cacheUserListV3_(cache, users);
  NOVA_RUNTIME_CACHE_.userIndex = index; // NOVA_USER_INDEX_RUNTIME_CACHE_V1
  return index;
}

function buildUserIndexFromListV3_(users) { // (분할 캐시 사용자목록을 기존 인덱스 구조로 복원)
  const index = { byName: {}, byEmployeeNo: {}, active: [] };
  (Array.isArray(users) ? users : []).forEach(user => {
    if (!user || !user.employeeNo || !user.name) return;
    index.byEmployeeNo[user.employeeNo] = user;
    if (!index.byName[user.name]) index.byName[user.name] = [];
    index.byName[user.name].push(user);
    if (user.enabled) index.active.push(user);
  });
  return index;
}

function readCachedUserListV3_(cache) { // (CacheService 100KB/key 제한을 피한 분할 사용자 캐시 조회)
  let meta = null;
  try { meta = JSON.parse(cache.get(NOVA_USER_INDEX_CACHE_META_V3_) || 'null'); }
  catch (error) { return null; }
  const chunkCount = Number(meta && meta.chunkCount || 0);
  if (!Number.isFinite(chunkCount) || chunkCount < 1 || chunkCount > 100) return null;
  const keys = Array.from({ length: chunkCount }, (_, index) => `${NOVA_USER_INDEX_CACHE_CHUNK_PREFIX_V3_}${index}`);
  let cached = {};
  try { cached = cache.getAll(keys) || {}; } catch (error) { return null; }
  const users = [];
  for (const key of keys) {
    if (!cached[key]) return null;
    let chunk = null;
    try { chunk = JSON.parse(cached[key]); } catch (error) { return null; }
    if (!Array.isArray(chunk)) return null;
    users.push.apply(users, chunk);
  }
  if (Number(meta.total || users.length) !== users.length) return null;
  return users;
}

function cacheUserListV3_(cache, users) { // (사용자 객체를 중복 인덱스가 아닌 1회 목록으로 분할 저장)
  const list = Array.isArray(users) ? users : [];
  if (!list.length) return false;
  const ttl = Number(NOVA.CACHE_SECONDS || 300);
  const payload = {};
  let chunkCount = 0;
  for (let index = 0; index < list.length; index += NOVA_USER_INDEX_CACHE_CHUNK_SIZE_V3_) {
    const serialized = JSON.stringify(list.slice(index, index + NOVA_USER_INDEX_CACHE_CHUNK_SIZE_V3_));
    if (serialized.length >= 95000) return false;
    payload[`${NOVA_USER_INDEX_CACHE_CHUNK_PREFIX_V3_}${chunkCount}`] = serialized;
    chunkCount += 1;
  }
  try {
    cache.putAll(payload, ttl);
    cache.put(NOVA_USER_INDEX_CACHE_META_V3_, JSON.stringify({ version: 3, chunkCount, total: list.length }), ttl);
    return true;
  } catch (error) {
    return false;
  }
}

'''
repository = repository[:start] + new_user_index + repository[end:]
repository = replace_once(
    repository,
    "    'NOVA_USER_INDEX_V2',\n    'NOVA_CODE_INDEX_V2',",
    "    'NOVA_USER_INDEX_V2',\n    NOVA_USER_INDEX_CACHE_META_V3_,\n    'NOVA_CODE_INDEX_V2',",
    "user cache invalidation"
)
repository_path.write_text(repository, encoding="utf-8")

# 2) Roommaid close: share result cache across authorized ADMIN/ORDER users and expose cold-read stage timings.
close_path = repo / "19_RoommaidCloseJournal.js"
close = close_path.read_text(encoding="utf-8")
close = replace_once(
    close,
    "function getRoommaidCloseJournal(token, filters) { // (룸메이드 마감일지 조회 · ROOMMAID_CLOSE_READ_ACCEL_V3)\n  return measureResponse_('getRoommaidCloseJournal', () => {\n    const user = requireRole_(token, ['ADMIN', 'ORDER']);",
    "function getRoommaidCloseJournal(token, filters) { // (룸메이드 마감일지 조회 · ROOMMAID_CLOSE_READ_ACCEL_V6)\n  return measureResponse_('getRoommaidCloseJournal', () => {\n    const traceStartedAt = Date.now(); // ROOMMAID_CLOSE_COLD_TIMING_V6\n    const timingsMs = {};\n    let stageStartedAt = Date.now();\n    const user = requireRole_(token, ['ADMIN', 'ORDER']);\n    timingsMs.auth = Date.now() - stageStartedAt;",
    "close timing start"
)
close = replace_once(
    close,
    "    const cacheKey = buildDeltaCacheKey_('ROOMMAID_CLOSE_READ_V3', [\n      NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION,\n      businessDate,\n      preferredSite,\n      String(user.employeeNo || ''),\n      sourceVersion,",
    "    const cacheKey = buildDeltaCacheKey_('ROOMMAID_CLOSE_READ_V4', [ // ROOMMAID_CLOSE_SHARED_CACHE_V6\n      NOVA_ROOMMAID_CLOSE.SCHEMA_VERSION,\n      businessDate,\n      preferredSite,\n      sourceVersion,",
    "shared close cache key"
)
close = replace_once(
    close,
    "    const cached = getCachedJson_(cacheKey);\n    if (cached && cached.ok) {\n      return Object.assign({}, cached, {\n        optimization: Object.assign({}, cached.optimization || {}, { cacheHit: true })\n      });\n    }\n\n    // 업무이력은 날짜 TextFinder로 후보행만 읽습니다. 전체 업무이력 열 스캔을 제거합니다.\n    const historyBundle = readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, preferredSite);",
    "    const cached = getCachedJson_(cacheKey);\n    if (cached && cached.ok) {\n      return Object.assign({}, cached, {\n        optimization: Object.assign({}, cached.optimization || {}, {\n          cacheHit: true,\n          cacheReturnMs: Date.now() - traceStartedAt\n        })\n      });\n    }\n\n    // 업무이력은 날짜 TextFinder로 후보행만 읽습니다. 전체 업무이력 열 스캔을 제거합니다.\n    stageStartedAt = Date.now();\n    const historyBundle = readRoommaidCloseHistoryBundleDbFirst_(token, businessDate, preferredSite);\n    timingsMs.history = Date.now() - stageStartedAt;",
    "history timing"
)
close = replace_once(
    close,
    "    let currentRows = [];\n    let currentSource = 'SHEET';\n    if (!saved) {",
    "    let currentRows = [];\n    let currentSource = 'SHEET';\n    stageStartedAt = Date.now();\n    if (!saved) {",
    "current timing start"
)
close = replace_once(
    close,
    "    if (!currentRows.length) throw new Error(`${businessDate} ${preferredSite} 현재객실현황이 없습니다.`);\n\n    const users = getUserIndex_().byEmployeeNo;",
    "    if (!currentRows.length) throw new Error(`${businessDate} ${preferredSite} 현재객실현황이 없습니다.`);\n    timingsMs.current = Date.now() - stageStartedAt;\n\n    stageStartedAt = Date.now();\n    const users = getUserIndex_().byEmployeeNo;\n    timingsMs.users = Date.now() - stageStartedAt;",
    "current/users timing"
)
close = replace_once(
    close,
    "    const liveSnapshot = buildRoommaidCloseLiveSnapshotFast_(businessDate, preferredSite, {",
    "    stageStartedAt = Date.now();\n    const liveSnapshot = buildRoommaidCloseLiveSnapshotFast_(businessDate, preferredSite, {",
    "build timing start"
)
close = replace_once(
    close,
    "    }); // ROOMMAID_CLOSE_COLD_READ_V5\n    const latestSourceAt = latestRoommaidCloseSourceAt_(currentRows, historyRows);",
    "    }); // ROOMMAID_CLOSE_COLD_READ_V5\n    timingsMs.build = Date.now() - stageStartedAt;\n    const latestSourceAt = latestRoommaidCloseSourceAt_(currentRows, historyRows);",
    "build timing end"
)
close = replace_once(
    close,
    "        marker: 'ROOMMAID_CLOSE_READ_ACCEL_V3',\n        cacheHit: false,",
    "        marker: 'ROOMMAID_CLOSE_READ_ACCEL_V6',\n        cacheHit: false,",
    "optimization marker"
)
close = replace_once(
    close,
    "        historyRowCount: historyRows.length,\n        historyLookup: String(historyBundle.readPath || (historyBundle.dbFirst ? 'DB_NATIVE' : 'DATE_TEXTFINDER'))\n      }\n    };\n    putCachedJson_(cacheKey, result, 120); // ROOMMAID_CLOSE_RESULT_CACHE_120S_V1\n    return result;",
    "        historyRowCount: historyRows.length,\n        historyLookup: String(historyBundle.readPath || (historyBundle.dbFirst ? 'DB_NATIVE' : 'DATE_TEXTFINDER')),\n        timingsMs\n      }\n    };\n    timingsMs.totalBeforeCachePut = Date.now() - traceStartedAt;\n    const cachePutStartedAt = Date.now();\n    putCachedJson_(cacheKey, result, 120); // ROOMMAID_CLOSE_RESULT_CACHE_120S_V1 · ROOMMAID_CLOSE_SHARED_CACHE_V6\n    timingsMs.cachePut = Date.now() - cachePutStartedAt;\n    timingsMs.total = Date.now() - traceStartedAt;\n    return result;",
    "result timings"
)
close_path.write_text(close, encoding="utf-8")

print("ROOMMAID_CLOSE_COLD_READ_V6_PATCHED")
