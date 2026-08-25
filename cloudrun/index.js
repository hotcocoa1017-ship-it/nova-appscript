import express from 'express';
import crypto from 'crypto';
import jwt from 'jsonwebtoken';
import pg from 'pg';

const { Pool } = pg;
const app = express();
app.disable('x-powered-by');
app.use(express.json({
  limit: '15mb',
  verify: (req, _res, buf) => {
    req.rawBody = buf.toString('utf8');
  }
}));

const NOVA_REALTIME_BUILD = 'phase1-v3.8-houseman-create';
const PORT = Number(process.env.PORT || 8080);
const DATABASE_URL = process.env.DATABASE_URL || '';
const PG_HOST = process.env.PG_HOST || '';
const PG_PORT = Number(process.env.PG_PORT || 6543);
const PG_USER = process.env.PG_USER || '';
const PG_PASSWORD = process.env.PG_PASSWORD || '';
const PG_DATABASE = process.env.PG_DATABASE || 'postgres';
const NOVA_TOKEN_SECRET = process.env.NOVA_TOKEN_SECRET || '';
const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_PUBLISHABLE_KEY = process.env.SUPABASE_PUBLISHABLE_KEY || '';
const SUPABASE_JWT_SECRET = process.env.SUPABASE_JWT_SECRET || '';

const HAS_PG_PARTS = Boolean(PG_HOST && PG_USER && PG_PASSWORD && PG_DATABASE);
if ((!DATABASE_URL && !HAS_PG_PARTS) || !NOVA_TOKEN_SECRET) {
  throw new Error('PostgreSQL 연결정보와 NOVA_TOKEN_SECRET 환경변수가 필요합니다.');
}

const poolConfig = {
  max: Number(process.env.PG_POOL_MAX || 20),
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
  ssl: process.env.PG_SSL === 'false' ? false : { rejectUnauthorized: false }
};

if (HAS_PG_PARTS) {
  Object.assign(poolConfig, {
    host: PG_HOST,
    port: PG_PORT,
    user: PG_USER,
    password: PG_PASSWORD,
    database: PG_DATABASE
  });
} else {
  poolConfig.connectionString = DATABASE_URL;
}

const pool = new Pool(poolConfig);

function httpError(status, code, message, extra = {}) {
  const e = new Error(message);
  e.status = status;
  e.code = code;
  Object.assign(e, extra);
  return e;
}

function normalizeBase64Url_(value) {
  return String(value || '').trim().replace(/=+$/g, '');
}

function verifyNovaToken(token) {
  const parts = String(token || '').trim().split('.');
  if (parts.length !== 2) throw httpError(401, 'UNAUTHORIZED', '로그인이 필요합니다.');
  const [body, rawSig] = parts;
  const sig = normalizeBase64Url_(rawSig);
  const expected = normalizeBase64Url_(
    crypto.createHmac('sha256', NOVA_TOKEN_SECRET).update(body).digest('base64url')
  );
  const a = Buffer.from(sig, 'utf8');
  const b = Buffer.from(expected, 'utf8');

  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    throw httpError(401, 'UNAUTHORIZED', '로그인 정보가 올바르지 않습니다.');
  }

  let payload;
  try {
    payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
  } catch {
    throw httpError(401, 'UNAUTHORIZED', '로그인 정보가 올바르지 않습니다.');
  }

  if (!payload?.employeeNo || !payload?.expiresAt || Date.now() > Number(payload.expiresAt)) {
    throw httpError(401, 'UNAUTHORIZED', '로그인 시간이 만료되었습니다.');
  }

  return payload;
}

function authBearer(req) {
  const value = String(req.headers.authorization || '');
  if (!value.startsWith('Bearer ')) {
    throw httpError(401, 'UNAUTHORIZED', '로그인이 필요합니다.');
  }
  return verifyNovaToken(value.slice(7));
}

function verifyMigrationSignature(req) {
  const timestamp = String(req.headers['x-nova-timestamp'] || '').trim();
  const signature = String(req.headers['x-nova-signature'] || '').trim().toLowerCase();
  const ts = Number(timestamp);

  if (!timestamp || !signature || !Number.isFinite(ts)) {
    throw httpError(401, 'MIGRATION_UNAUTHORIZED', '이관 인증정보가 없습니다.');
  }

  if (Math.abs(Date.now() - ts) > 5 * 60 * 1000) {
    throw httpError(401, 'MIGRATION_EXPIRED', '이관 인증시간이 만료되었습니다.');
  }

  const rawBody = typeof req.rawBody === 'string'
    ? req.rawBody
    : JSON.stringify(req.body || {});

  const expected = crypto
    .createHmac('sha256', NOVA_TOKEN_SECRET)
    .update(`${timestamp}.${rawBody}`)
    .digest('hex');

  const a = Buffer.from(signature, 'utf8');
  const b = Buffer.from(expected, 'utf8');

  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    throw httpError(401, 'MIGRATION_UNAUTHORIZED', '이관 인증정보가 올바르지 않습니다.');
  }

  return true;
}

async function loadUser(client, employeeNo) {
  const { rows } = await client.query(
    `select employee_no, name, role, enabled, default_site, allowed_sites
       from public.nova_users
      where employee_no=$1`,
    [String(employeeNo)]
  );

  const user = rows[0];

  if (!user || !user.enabled) {
    throw httpError(401, 'UNAUTHORIZED', '사용할 수 없는 계정입니다.');
  }

  return user;
}

function allowedForSite(user, site) {
  if (['ADMIN', 'ORDER'].includes(user.role)) return true;

  // Phase 1의 ROOMMAID/QM 객실 접근권한은 '기본사업장'이 아니라
  // 실제 객실 배정정보로 판정합니다.
  if (['ROOMMAID', 'QM'].includes(user.role)) {
    return Boolean(String(site || '').trim());
  }

  const allowed = new Set([
    ...(user.allowed_sites || []),
    user.default_site
  ].filter(Boolean));

  return allowed.has(site);
}

function canCleanRoom(user, room) {
  if (['ADMIN', 'ORDER'].includes(user.role)) return true;
  if (user.role !== 'ROOMMAID') return false;

  return room.roommaid_employee_no === user.employee_no
    || room.secondary_roommaid_employee_no === user.employee_no;
}

function roomDto(r) {
  return {
    businessDate: r.business_date instanceof Date
      ? r.business_date.toISOString().slice(0, 10)
      : String(r.business_date || ''),
    site: r.site || '',
    roomNo: r.room_no || '',
    building: r.building || '',
    roomStatus: r.room_status || '',
    cleaningStatus: r.cleaning_status || '',
    cleaningType: r.cleaning_type || 'NORMAL',
    assignmentType: r.assignment_type || 'SOLO',
    roommaidEmployeeNo: r.roommaid_employee_no || '',
    secondaryRoommaidEmployeeNo: r.secondary_roommaid_employee_no || '',
    qmEmployeeNo: r.qm_employee_no || '',
    operationalStatus: r.operational_status || '',
    version: Number(r.version || 0),
    updatedAt: r.updated_at || ''
  };
}

const HOUSEMAN_STATUS_LABELS_ = Object.freeze({
  REGISTERED: '등록',
  ASSIGNED: '배정',
  ACCEPTED: '접수',
  PROCESSING: '처리중',
  COMPLETED: '완료',
  UNABLE: '처리불가'
});

function koreaDateTimeText_(value) {
  if (!value) return '';

  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value || '');
  }

  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    hourCycle: 'h23'
  }).formatToParts(date).reduce((acc, part) => {
    acc[part.type] = part.value;
    return acc;
  }, {});

  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
}

function dateOnlyText_(value) {
  if (!value) return '';

  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }

  return String(value || '').slice(0, 10);
}

function housemanOrderDto_(r) {
  const statusCode =
    cleanText_(r?.status_code, 30).toUpperCase() || 'REGISTERED';

  return {
    rowNumber: 0,
    orderId: cleanText_(r?.order_id, 80),
    businessDate: dateOnlyText_(r?.business_date),
    site: cleanText_(r?.site, 80),
    roomNo: cleanText_(r?.room_no, 40),
    part: cleanText_(r?.part, 80),
    items: Array.isArray(r?.items) ? r.items : [],
    itemSummary: cleanText_(r?.item_summary, 1000),
    quantity: Number(r?.quantity || 0),
    note: String(r?.note || ''),
    requester: cleanText_(r?.requester, 120),
    assignedEmployeeNo: cleanText_(r?.assigned_employee_no, 80),
    assignedName: cleanText_(r?.assigned_name, 120),
    processorEmployeeNo: cleanText_(r?.processor_employee_no, 80),
    processorName: cleanText_(r?.processor_name, 120),
    statusCode,
    statusLabel: HOUSEMAN_STATUS_LABELS_[statusCode] || statusCode,
    important: r?.important === true,
    handover: r?.handover === true,
    handoverTargetShift:
      cleanText_(r?.handover_target_shift, 10).toUpperCase(),
    assignmentMode:
      cleanText_(r?.assignment_mode, 20).toUpperCase() || 'UNASSIGNED',
    autoAssigned: r?.auto_assigned === true,
    assignedBuilding: cleanText_(r?.assigned_building, 40),
    assignedShiftCode:
      cleanText_(r?.assigned_shift_code, 10).toUpperCase(),
    assignedShiftCodes:
      Array.isArray(r?.assigned_shift_codes)
        ? r.assigned_shift_codes
        : [],
    routeCandidateEmployeeNos:
      Array.isArray(r?.route_candidate_employee_nos)
        ? r.route_candidate_employee_nos
        : [],
    routeCandidateNames:
      Array.isArray(r?.route_candidate_names)
        ? r.route_candidate_names
        : [],
    routeCandidateSummary:
      (Array.isArray(r?.route_candidate_names)
        ? r.route_candidate_names
        : []).join(' · '),
    routeLocked: r?.route_locked !== false,
    acceptedByEmployeeNo:
      cleanText_(r?.accepted_by_employee_no, 80),
    releasedCandidateEmployeeNos:
      Array.isArray(r?.released_candidate_employee_nos)
        ? r.released_candidate_employee_nos
        : [],
    registeredBy: cleanText_(r?.registered_by, 80),
    registeredAt: koreaDateTimeText_(r?.registered_at),
    acceptedAt: koreaDateTimeText_(r?.accepted_at),
    startedAt: koreaDateTimeText_(r?.started_at),
    completedAt: koreaDateTimeText_(r?.completed_at),
    unableReason: String(r?.unable_reason || ''),
    updatedAt: koreaDateTimeText_(r?.updated_at),
    version: Number(r?.version || 0)
  };
}

function normalizeHousemanItems_(rawItems) {
  if (!Array.isArray(rawItems)) return [];

  return rawItems
    .slice(0, 50)
    .map(raw => ({
      name: cleanText_(raw?.name, 160),
      quantity: Math.max(
        1,
        Math.min(99, Number(raw?.quantity || 1))
      )
    }))
    .filter(item => item.name);
}

function normalizeShiftCodes_(raw) {
  return Array.from(
    new Set(
      (Array.isArray(raw) ? raw : [])
        .map(value => cleanText_(value, 10).toUpperCase())
        .filter(value => ['A', 'B', 'C'].includes(value))
    )
  );
}

function chunkArray_(items, size) {
  const chunks = [];

  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }

  return chunks;
}

function cleanText_(value, max = 200) {
  return String(value ?? '').trim().slice(0, max);
}

function normalizeMigrationUser_(raw, knownSites) {
  const role = cleanText_(raw?.role, 20).toUpperCase();

  if (![
    'ADMIN',
    'ORDER',
    'QM',
    'HOUSEMAN',
    'ROOMMAID',
    'PUBLIC'
  ].includes(role)) {
    return null;
  }

  const employeeNo = cleanText_(raw?.employeeNo, 40);
  const name = cleanText_(raw?.name, 80);

  if (!employeeNo || !name) return null;

  const defaultSite = cleanText_(raw?.defaultSite, 80);

  let allowedSites = Array.isArray(raw?.allowedSites)
    ? raw.allowedSites
        .map(v => cleanText_(v, 80))
        .filter(Boolean)
    : [];

  if (['ADMIN', 'ORDER'].includes(role)) {
    allowedSites = [...knownSites];
  } else if (!allowedSites.length && defaultSite) {
    allowedSites = [defaultSite];
  }

  allowedSites = Array.from(new Set(allowedSites));

  return {
    employeeNo,
    name,
    role,
    enabled: raw?.enabled !== false,
    defaultSite,
    allowedSites
  };
}

function normalizeMigrationRoom_(raw) {
  const businessDate = cleanText_(raw?.businessDate, 20);
  const site = cleanText_(raw?.site, 80);
  const roomNo = cleanText_(raw?.roomNo, 40);

  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(businessDate)
    || !site
    || !roomNo
  ) {
    return null;
  }

  return {
    businessDate,
    site,
    roomNo,
    building: cleanText_(raw?.building, 80),
    roomStatus: cleanText_(raw?.roomStatus, 40),
    cleaningStatus:
      cleanText_(
        raw?.cleaningStatus || 'WAITING',
        40
      ).toUpperCase(),
    cleaningType:
      cleanText_(
        raw?.cleaningType || 'NORMAL',
        40
      ).toUpperCase(),
    assignmentType:
      cleanText_(
        raw?.assignmentType || 'SOLO',
        40
      ).toUpperCase(),
    roommaidEmployeeNo:
      cleanText_(raw?.roommaidEmployeeNo, 40),
    secondaryRoommaidEmployeeNo:
      cleanText_(raw?.secondaryRoommaidEmployeeNo, 40),
    qmEmployeeNo:
      cleanText_(raw?.qmEmployeeNo, 40),
    operationalStatus:
      cleanText_(raw?.operationalStatus, 80)
  };
}

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');

  res.setHeader(
    'Access-Control-Allow-Headers',
    'Authorization, Content-Type, X-Request-Id, X-NOVA-Timestamp, X-NOVA-Signature'
  );

  res.setHeader(
    'Access-Control-Allow-Methods',
    'GET, POST, OPTIONS'
  );

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  next();
});

app.get('/health', async (_req, res, next) => {
  try {
    const { rows } = await pool.query('select now() now');

    res.json({
      ok: true,
      build: NOVA_REALTIME_BUILD,
      dbTime: rows[0].now,
      dbConfigMode:
        HAS_PG_PARTS ? 'PG_PARTS' : 'DATABASE_URL'
    });
  } catch (e) {
    next(e);
  }
});

app.get('/healthz', async (_req, res, next) => {
  try {
    const { rows } = await pool.query('select now() now');

    res.json({
      ok: true,
      build: NOVA_REALTIME_BUILD,
      dbTime: rows[0].now,
      dbConfigMode:
        HAS_PG_PARTS ? 'PG_PARTS' : 'DATABASE_URL'
    });
  } catch (e) {
    next(e);
  }
});

/**
 * 최초 1회 부트스트랩 이관.
 */
app.post('/v1/admin/bootstrap-import', async (req, res, next) => {
  const startedAt = Date.now();
  let client;

  try {
    verifyMigrationSignature(req);

    const body = req.body || {};
    const rawUsers =
      Array.isArray(body.users) ? body.users : [];
    const rawRooms =
      Array.isArray(body.rooms) ? body.rooms : [];
    const forceSheetCleaning =
      body.forceSheetCleaning === true;

    if (!rawUsers.length) {
      throw httpError(
        400,
        'MIGRATION_NO_USERS',
        '이관할 사용자계정이 없습니다.'
      );
    }

    if (!rawRooms.length) {
      throw httpError(
        400,
        'MIGRATION_NO_ROOMS',
        '이관할 현재객실현황이 없습니다.'
      );
    }

    if (
      rawUsers.length > 5000
      || rawRooms.length > 30000
    ) {
      throw httpError(
        400,
        'MIGRATION_TOO_LARGE',
        '이관 데이터가 허용 범위를 초과했습니다. 사용자 5,000명 / 객실 30,000건 이하로 실행하세요.'
      );
    }

    const knownSites = Array.from(
      new Set(
        rawRooms
          .map(r => cleanText_(r?.site, 80))
          .filter(Boolean)
      )
    );

    const users =
      rawUsers
        .map(r =>
          normalizeMigrationUser_(r, knownSites)
        )
        .filter(Boolean);

    const rooms =
      rawRooms
        .map(normalizeMigrationRoom_)
        .filter(Boolean);

    if (!users.length || !rooms.length) {
      throw httpError(
        400,
        'MIGRATION_INVALID_DATA',
        '유효한 이관 데이터를 확인하지 못했습니다.'
      );
    }

    const userKeys = new Set();

    for (const user of users) {
      if (userKeys.has(user.employeeNo)) {
        throw httpError(
          400,
          'MIGRATION_DUP_USER',
          `중복 사번이 있습니다: ${user.employeeNo}`
        );
      }

      userKeys.add(user.employeeNo);
    }

    const roomKeys = new Set();

    for (const room of rooms) {
      const key =
        `${room.businessDate}|${room.site}|${room.roomNo}`;

      if (roomKeys.has(key)) {
        throw httpError(
          400,
          'MIGRATION_DUP_ROOM',
          `중복 객실이 있습니다: ${key}`
        );
      }

      roomKeys.add(key);
    }

    client = await pool.connect();

    await client.query('begin');

    const locked = await client.query(`
      select
        (
          select count(*)::int
          from public.nova_room_events
        ) as event_count,
        (
          select count(*)::int
          from public.nova_request_dedup
        ) as request_count
    `);

    const eventCount =
      Number(locked.rows[0]?.event_count || 0);

    const requestCount =
      Number(locked.rows[0]?.request_count || 0);

    if (eventCount > 0 || requestCount > 0) {
      throw httpError(
        409,
        'BOOTSTRAP_LOCKED',
        '실시간 처리 이력이 존재하여 최초 이관을 다시 실행할 수 없습니다.'
      );
    }

    await client.query(
      'delete from public.nova_rooms_current'
    );

    await client.query(
      'delete from public.nova_users'
    );

    for (const group of chunkArray_(users, 250)) {
      const params = [];

      const values = group.map((u, i) => {
        const n = i * 6;

        params.push(
          u.employeeNo,
          u.name,
          u.role,
          u.enabled,
          u.defaultSite || null,
          u.allowedSites
        );

        return `(
          $${n + 1},
          $${n + 2},
          $${n + 3},
          $${n + 4},
          $${n + 5},
          $${n + 6}::text[]
        )`;
      }).join(',');

      await client.query(`
        insert into public.nova_users(
          employee_no,
          name,
          role,
          enabled,
          default_site,
          allowed_sites
        )
        values ${values}
      `, params);
    }

    for (const group of chunkArray_(rooms, 200)) {
      const params = [];

      const values = group.map((r, i) => {
        const n = i * 12;

        params.push(
          r.businessDate,
          r.site,
          r.roomNo,
          r.building || null,
          r.roomStatus,
          r.cleaningStatus,
          r.cleaningType,
          r.assignmentType,
          r.roommaidEmployeeNo || null,
          r.secondaryRoommaidEmployeeNo || null,
          r.qmEmployeeNo || null,
          r.operationalStatus
        );

        return `(
          $${n + 1}::date,
          $${n + 2},
          $${n + 3},
          $${n + 4},
          $${n + 5},
          $${n + 6},
          $${n + 7},
          $${n + 8},
          $${n + 9},
          $${n + 10},
          $${n + 11},
          $${n + 12}
        )`;
      }).join(',');

      await client.query(`
        insert into public.nova_rooms_current(
          business_date,
          site,
          room_no,
          building,
          room_status,
          cleaning_status,
          cleaning_type,
          assignment_type,
          roommaid_employee_no,
          secondary_roommaid_employee_no,
          qm_employee_no,
          operational_status
        )
        values ${values}
      `, params);
    }

    await client.query('commit');

    res.json({
      ok: true,
      mode: 'BOOTSTRAP_IMPORT',
      usersImported: users.length,
      roomsImported: rooms.length,
      sites: knownSites,
      source:
        cleanText_(
          body.source || 'GOOGLE_SHEETS',
          50
        ),
      importedAt: new Date().toISOString(),
      timing: {
        totalMs: Date.now() - startedAt
      }
    });

  } catch (e) {

    if (client) {
      try {
        await client.query('rollback');
      } catch {}
    }

    next(e);

  } finally {

    if (client) {
      client.release();
    }
  }
});

/**
 * 운영 중 현재객실현황 증분 동기화.
 */
app.post(
  '/v1/admin/sync-current-rooms',
  async (req, res, next) => {

    const startedAt = Date.now();
    let client;

    try {
      verifyMigrationSignature(req);

      const body = req.body || {};
      const businessDate =
        cleanText_(body.businessDate, 20);

      const rawUsers =
        Array.isArray(body.users)
          ? body.users
          : [];

      const rawRooms =
        Array.isArray(body.rooms)
          ? body.rooms
          : [];

      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(businessDate)
      ) {
        throw httpError(
          400,
          'SYNC_INVALID_DATE',
          '동기화 업무일자가 올바르지 않습니다.'
        );
      }

      if (!rawRooms.length) {
        return res.json({
          ok: true,
          mode: 'CURRENT_ROOMS_SYNC',
          businessDate,
          usersSynced: 0,
          roomsSynced: 0,
          skipped: true,
          timing: {
            totalMs:
              Date.now() - startedAt
          }
        });
      }

      if (
        rawUsers.length > 5000
        || rawRooms.length > 5000
      ) {
        throw httpError(
          400,
          'SYNC_TOO_LARGE',
          '증분 동기화 데이터가 허용 범위를 초과했습니다. 사용자 5,000명 / 객실 5,000건 이하로 실행하세요.'
        );
      }

      const knownSites = Array.from(
        new Set(
          rawRooms
            .map(r => cleanText_(r?.site, 80))
            .filter(Boolean)
        )
      );

      const users =
        rawUsers
          .map(r =>
            normalizeMigrationUser_(
              r,
              knownSites
            )
          )
          .filter(Boolean);

      const rooms =
        rawRooms
          .map(normalizeMigrationRoom_)
          .filter(Boolean);

      if (!rooms.length) {
        throw httpError(
          400,
          'SYNC_INVALID_DATA',
          '유효한 객실 동기화 데이터를 확인하지 못했습니다.'
        );
      }

      for (const room of rooms) {
        if (
          room.businessDate !== businessDate
        ) {
          throw httpError(
            400,
            'SYNC_DATE_MISMATCH',
            `업무일자가 다른 객실이 포함되어 있습니다: ${room.site} ${room.roomNo}`
          );
        }
      }

      client = await pool.connect();

      await client.query('begin');

      for (
        const group
        of chunkArray_(users, 250)
      ) {
        const params = [];

        const values =
          group.map((u, i) => {

            const n = i * 6;

            params.push(
              u.employeeNo,
              u.name,
              u.role,
              u.enabled,
              u.defaultSite || null,
              u.allowedSites
            );

            return `(
              $${n + 1},
              $${n + 2},
              $${n + 3},
              $${n + 4},
              $${n + 5},
              $${n + 6}::text[]
            )`;

          }).join(',');

        await client.query(`
          insert into public.nova_users(
            employee_no,
            name,
            role,
            enabled,
            default_site,
            allowed_sites
          )
          values ${values}

          on conflict(employee_no)
          do update set
            name=excluded.name,
            role=excluded.role,
            enabled=excluded.enabled,
            default_site=excluded.default_site,
            allowed_sites=excluded.allowed_sites
        `, params);
      }

      for (
        const group
        of chunkArray_(rooms, 200)
      ) {

        const params = [];

        const values =
          group.map((r, i) => {

            const n = i * 12;

            params.push(
              r.businessDate,
              r.site,
              r.roomNo,
              r.building || null,
              r.roomStatus,
              r.cleaningStatus,
              r.cleaningType,
              r.assignmentType,
              r.roommaidEmployeeNo || null,
              r.secondaryRoommaidEmployeeNo || null,
              r.qmEmployeeNo || null,
              r.operationalStatus
            );

            return `(
              $${n + 1}::date,
              $${n + 2},
              $${n + 3},
              $${n + 4},
              $${n + 5},
              $${n + 6},
              $${n + 7},
              $${n + 8},
              $${n + 9},
              $${n + 10},
              $${n + 11},
              $${n + 12}
            )`;

          }).join(',');

        await client.query(`
          insert into public.nova_rooms_current(
            business_date,
            site,
            room_no,
            building,
            room_status,
            cleaning_status,
            cleaning_type,
            assignment_type,
            roommaid_employee_no,
            secondary_roommaid_employee_no,
            qm_employee_no,
            operational_status
          )
          values ${values}

          on conflict(
            business_date,
            site,
            room_no
          )
          do update set
            building=excluded.building,
            room_status=excluded.room_status,

            cleaning_status=
              case
                when ${forceSheetCleaning ? 'true' : 'false'}
                  then excluded.cleaning_status
                when public.nova_rooms_current.updated_by is null
                  then excluded.cleaning_status
                else public.nova_rooms_current.cleaning_status
              end,

            cleaning_type=excluded.cleaning_type,
            assignment_type=excluded.assignment_type,

            roommaid_employee_no=
              excluded.roommaid_employee_no,

            secondary_roommaid_employee_no=
              excluded.secondary_roommaid_employee_no,

            qm_employee_no=
              excluded.qm_employee_no,

            operational_status=
              excluded.operational_status,

            version=
              case
                when ${forceSheetCleaning ? 'true' : 'false'}
                  then 0
                when public.nova_rooms_current.updated_by is null
                  then 0
                else public.nova_rooms_current.version
              end,

            updated_by=
              case
                when ${forceSheetCleaning ? 'true' : 'false'}
                  then null
                else public.nova_rooms_current.updated_by
              end,

            updated_at=now()
        `, params);
      }

      await client.query('commit');

      res.json({
        ok: true,
        mode: 'CURRENT_ROOMS_SYNC',
        businessDate,
        sites: knownSites,
        usersSynced: users.length,
        roomsSynced: rooms.length,
        forceSheetCleaning,
        syncedAt: new Date().toISOString(),
        timing: {
          totalMs:
            Date.now() - startedAt
        }
      });

    } catch (e) {

      if (client) {
        try {
          await client.query('rollback');
        } catch {}
      }

      next(e);

    } finally {

      if (client) {
        client.release();
      }
    }
  }
);

/**
 * PostgreSQL에서 발생한 룸메이드 청소 이벤트를 Apps Script가 배치로 회수.
 */
app.post(
  '/v1/admin/realtime-events',
  async (req, res, next) => {

    const startedAt = Date.now();
    let client;

    try {
      verifyMigrationSignature(req);

      const body = req.body || {};

      const businessDate =
        cleanText_(body.businessDate, 20);

      const cursorTime =
        cleanText_(body.cursorTime, 80)
        || '1970-01-01T00:00:00.000Z';

      const cursorRequestId =
        cleanText_(body.cursorRequestId, 200);

      const limit =
        Math.max(
          1,
          Math.min(
            1000,
            Number(body.limit || 500)
          )
        );

      if (
        businessDate
        && !/^\d{4}-\d{2}-\d{2}$/.test(
          businessDate
        )
      ) {
        throw httpError(
          400,
          'EVENT_SYNC_INVALID_DATE',
          '이벤트 동기화 업무일자가 올바르지 않습니다.'
        );
      }

      client = await pool.connect();

      const params = [
        cursorTime,
        cursorRequestId,
        limit
      ];

      let sql = `
        select
          request_id,
          business_date,
          site,
          room_no,
          action,
          before_status,
          after_status,
          employee_no,
          room_version,
          detail,
          event_time
        from public.nova_room_events
        where (
          event_time > $1::timestamptz
          or (
            event_time = $1::timestamptz
            and request_id > $2
          )
        )
      `;

      if (businessDate) {
        params.push(businessDate);
        sql += ` and business_date=$4::date`;
      }

      sql += `
        order by
          event_time asc,
          request_id asc
        limit $3
      `;

      const { rows } =
        await client.query(sql, params);

      const events = rows.map(row => ({
        requestId:
          String(row.request_id || ''),
        businessDate:
          row.business_date instanceof Date
            ? row.business_date
                .toISOString()
                .slice(0, 10)
            : String(
                row.business_date || ''
              ).slice(0, 10),
        site:
          String(row.site || ''),
        roomNo:
          String(row.room_no || ''),
        action:
          String(row.action || ''),
        beforeStatus:
          String(row.before_status || ''),
        afterStatus:
          String(row.after_status || ''),
        employeeNo:
          String(row.employee_no || ''),
        roomVersion:
          Number(row.room_version || 0),
        detail:
          row.detail || {},
        eventTime:
          row.event_time instanceof Date
            ? row.event_time.toISOString()
            : String(row.event_time || '')
      }));

      const last =
        events[events.length - 1] || null;

      res.json({
        ok: true,
        events,
        nextCursorTime:
          last
            ? last.eventTime
            : cursorTime,
        nextCursorRequestId:
          last
            ? last.requestId
            : cursorRequestId,
        hasMore:
          events.length >= limit,
        timing: {
          totalMs:
            Date.now() - startedAt
        }
      });

    } catch (e) {
      next(e);

    } finally {
      if (client) {
        client.release();
      }
    }
  }
);

/**
 * DB 이벤트를 Sheets/업무이력에 반영한 후
 * 소유권을 다시 Sheets로 넘김.
 */
app.post(
  '/v1/admin/ack-mirrored-events',
  async (req, res, next) => {

    const startedAt = Date.now();
    let client;

    try {
      verifyMigrationSignature(req);

      const items =
        Array.isArray(req.body?.items)
          ? req.body.items
          : [];

      if (items.length > 1000) {
        throw httpError(
          400,
          'ACK_TOO_LARGE',
          '미러 확인 요청은 1,000건 이하만 처리할 수 있습니다.'
        );
      }

      client = await pool.connect();

      await client.query('begin');

      let released = 0;

      for (const raw of items) {

        const businessDate =
          cleanText_(raw?.businessDate, 20);

        const site =
          cleanText_(raw?.site, 80);

        const roomNo =
          cleanText_(raw?.roomNo, 40);

        const roomVersion =
          Number(raw?.roomVersion || 0);

        if (
          !/^\d{4}-\d{2}-\d{2}$/.test(
            businessDate
          )
          || !site
          || !roomNo
          || roomVersion <= 0
        ) {
          continue;
        }

        const result =
          await client.query(`
            update public.nova_rooms_current

            set
              updated_by=null,
              updated_at=now()

            where
              business_date=$1::date
              and site=$2
              and room_no=$3
              and version=$4
          `, [
            businessDate,
            site,
            roomNo,
            roomVersion
          ]);

        released +=
          Number(result.rowCount || 0);
      }

      await client.query('commit');

      res.json({
        ok: true,
        requested: items.length,
        released,
        timing: {
          totalMs:
            Date.now() - startedAt
        }
      });

    } catch (e) {

      if (client) {
        try {
          await client.query('rollback');
        } catch {}
      }

      next(e);

    } finally {

      if (client) {
        client.release();
      }
    }
  }
);

app.get(
  '/v1/rooms',
  async (req, res, next) => {

    let client;

    try {
      client = await pool.connect();

      const auth =
        authBearer(req);

      const user =
        await loadUser(
          client,
          auth.employeeNo
        );

      const businessDate =
        String(
          req.query.businessDate || ''
        ).trim();

      const site =
        String(
          req.query.site || ''
        ).trim();

      if (!businessDate || !site) {
        throw httpError(
          400,
          'INVALID_REQUEST',
          '업무일자와 사업장이 필요합니다.'
        );
      }

      if (!allowedForSite(user, site)) {
        throw httpError(
          403,
          'FORBIDDEN',
          '해당 사업장 조회 권한이 없습니다.'
        );
      }

      let sql = `
        select *
        from public.nova_rooms_current
        where
          business_date=$1
          and site=$2
      `;

      const params = [
        businessDate,
        site
      ];

      if (user.role === 'ROOMMAID') {

        sql += `
          and (
            roommaid_employee_no=$3
            or secondary_roommaid_employee_no=$3
          )
        `;

        params.push(
          user.employee_no
        );

      } else if (user.role === 'QM') {

        sql += `
          and qm_employee_no=$3
        `;

        params.push(
          user.employee_no
        );

      } else if (
        !['ADMIN', 'ORDER'].includes(
          user.role
        )
      ) {

        throw httpError(
          403,
          'FORBIDDEN',
          '객실 조회 권한이 없습니다.'
        );
      }

      sql += ` order by room_no`;

      const { rows } =
        await client.query(
          sql,
          params
        );

      res.json({
        ok: true,
        rooms:
          rows.map(roomDto),
        serverTime:
          new Date().toISOString()
      });

    } catch (e) {
      next(e);

    } finally {
      if (client) {
        client.release();
      }
    }
  }
);

/**
 * ADMIN/ORDER 통합 인디케이터용 경량 DB 변경조회.
 */
app.get(
  '/v1/room-changes',
  async (req, res, next) => {

    let client;

    try {
      const auth =
        authBearer(req);

      client =
        await pool.connect();

      const user =
        await loadUser(
          client,
          auth.employeeNo
        );

      if (
        !['ADMIN', 'ORDER'].includes(
          user.role
        )
      ) {
        throw httpError(
          403,
          'FORBIDDEN',
          '통합 인디케이터 변경조회 권한이 없습니다.'
        );
      }

      const businessDate =
        cleanText_(
          req.query.businessDate,
          20
        );

      const site =
        cleanText_(
          req.query.site,
          80
        );

      const cursorTimeRaw =
        cleanText_(
          req.query.cursorTime,
          80
        );

      const cursorRequestId =
        cleanText_(
          req.query.cursorRequestId,
          200
        );

      const limit =
        Math.max(
          1,
          Math.min(
            500,
            Number(
              req.query.limit || 200
            )
          )
        );

      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(
          businessDate
        )
      ) {
        throw httpError(
          400,
          'INVALID_REQUEST',
          '업무일자가 필요합니다.'
        );
      }

      if (
        site
        && !allowedForSite(
          user,
          site
        )
      ) {
        throw httpError(
          403,
          'FORBIDDEN',
          '해당 사업장 조회 권한이 없습니다.'
        );
      }

      const upperResult =
        await client.query(`
          select now() as upper_time
        `);

      const upperTime =
        upperResult.rows[0].upper_time;

      const lowerTime =
        cursorTimeRaw
        || new Date(
          new Date(upperTime).getTime()
          - 15000
        ).toISOString();

      const params = [
        businessDate,
        lowerTime,
        cursorRequestId,
        upperTime,
        limit
      ];

      let sql = `
        select
          request_id,
          business_date,
          site,
          room_no,
          action,
          after_status,
          room_version,
          detail,
          event_time
        from public.nova_room_events
        where
          business_date=$1::date
          and (
            event_time > $2::timestamptz
            or (
              event_time = $2::timestamptz
              and request_id > $3
            )
          )
          and event_time <= $4::timestamptz
      `;

      if (site) {
        params.push(site);
        sql += ` and site=$6`;
      }

      sql += `
        order by
          event_time asc,
          request_id asc
        limit $5
      `;

      const { rows } =
        await client.query(
          sql,
          params
        );

      const changes =
        rows.map(row => {
          const action = String(row.action || '').trim().toUpperCase();
          const detail = row.detail && typeof row.detail === 'object' ? row.detail : {};
          const room = {
            businessDate:
              row.business_date instanceof Date
                ? row.business_date.toISOString().slice(0, 10)
                : String(row.business_date || '').slice(0, 10),
            site: String(row.site || ''),
            roomNo: String(row.room_no || ''),
            cleaningStatus: String(row.after_status || ''),
            version: Number(row.room_version || 0),
            updatedAt:
              row.event_time instanceof Date
                ? row.event_time.toISOString()
                : String(row.event_time || '')
          };
          if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
            delete room.cleaningStatus;
            room.operationalStatus = String(
              Object.prototype.hasOwnProperty.call(detail, 'operationalStatus')
                ? detail.operationalStatus
                : row.after_status || ''
            );
          }
          if (action === 'CHANGE_ROOM_STATUS') {
            delete room.cleaningStatus;
            room.roomStatus = String(detail.roomStatus || row.after_status || '');
            const roomPatch = detail.roomPatch && typeof detail.roomPatch === 'object' ? detail.roomPatch : {};
            [
              'cleaningStatus', 'cleaningType', 'assignmentType',
              'roommaidEmployeeNo', 'secondaryRoommaidEmployeeNo', 'qmEmployeeNo'
            ].forEach(key => {
              if (Object.prototype.hasOwnProperty.call(roomPatch, key)) room[key] = roomPatch[key];
            });
          }
          if (action === 'ASSIGN_ROOMMAID') {
            room.cleaningType = String(detail.cleaningType || 'NORMAL');
            room.assignmentType = String(detail.assignmentType || 'SOLO');
            room.roommaidEmployeeNo = String(detail.primaryEmployeeNo || '');
            room.secondaryRoommaidEmployeeNo = String(detail.secondaryEmployeeNo || '');
          }
          if (action === 'QM_ASSIGN') {
            room.qmEmployeeNo = String(detail.qmEmployeeNo || '');
          }
          return {
            requestId: String(row.request_id || ''),
            eventTime:
              row.event_time instanceof Date
                ? row.event_time.toISOString()
                : String(row.event_time || ''),
            room
          };
        });

      const hasMore =
        changes.length >= limit;

      const last =
        changes[
          changes.length - 1
        ] || null;

      res.json({
        ok: true,
        changes,
        nextCursorTime:
          hasMore && last
            ? last.eventTime
            : new Date(
                upperTime
              ).toISOString(),
        nextCursorRequestId:
          hasMore && last
            ? last.requestId
            : '',
        hasMore,
        serverTime:
          new Date(
            upperTime
          ).toISOString()
      });

    } catch (e) {
      next(e);

    } finally {
      if (client) {
        client.release();
      }
    }
  }
);

app.post(
  '/v1/rooms/:roomNo/action',
  async (req, res, next) => {

    const startedAt =
      Date.now();

    let client;

    try {
      client =
        await pool.connect();

      const auth =
        authBearer(req);

      const body =
        req.body || {};

      const businessDate =
        String(
          body.businessDate || ''
        ).trim();

      const site =
        String(
          body.site || ''
        ).trim();

      const roomNo =
        String(
          req.params.roomNo || ''
        ).trim();

      const action =
        String(
          body.action || ''
        ).trim().toUpperCase();

      const requestId =
        String(
          body.requestId
          || req.headers['x-request-id']
          || ''
        ).trim();

      const expectedVersion =
        Number(
          body.expectedVersion || 0
        );

      if (
        !businessDate
        || !site
        || !roomNo
        || !requestId
      ) {
        throw httpError(
          400,
          'INVALID_REQUEST',
          '업무일자·사업장·객실번호·requestId가 필요합니다.'
        );
      }

      if (
        !['CLEANING_START', 'CLEANING_COMPLETE', 'ASSIGN_ROOMMAID', 'QM_ASSIGN', 'CHANGE_ROOM_STATUS', 'UPDATE_ROOM_OPERATION_STATUS'].includes(action)
      ) {
        throw httpError(
          400,
          'INVALID_ACTION',
          '지원하지 않는 객실 작업입니다.'
        );
      }

      await client.query('begin');

      const user =
        await loadUser(
          client,
          auth.employeeNo
        );

      if (
        !allowedForSite(
          user,
          site
        )
      ) {
        throw httpError(
          403,
          'FORBIDDEN',
          '해당 사업장 처리 권한이 없습니다.'
        );
      }

      const inserted =
        await client.query(
          `
          insert into public.nova_request_dedup(
            request_id,
            employee_no,
            action
          )
          values($1,$2,$3)
          on conflict(request_id)
          do nothing
          returning request_id
          `,
          [
            requestId,
            user.employee_no,
            action
          ]
        );

      if (!inserted.rowCount) {

        const prior =
          await client.query(
            `
            select response_json
            from public.nova_request_dedup
            where request_id=$1
            `,
            [requestId]
          );

        await client.query('commit');

        if (
          prior.rows[0]?.response_json
        ) {
          return res.json({
            ...prior.rows[0].response_json,
            duplicateRequest: true
          });
        }

        throw httpError(
          409,
          'REQUEST_IN_PROGRESS',
          '동일 요청이 처리 중입니다.'
        );
      }

      const found =
        await client.query(
          `
          select *
          from public.nova_rooms_current
          where
            business_date=$1
            and site=$2
            and room_no=$3
          for update
          `,
          [
            businessDate,
            site,
            roomNo
          ]
        );

      const room =
        found.rows[0];

      if (!room) {
        throw httpError(
          404,
          'ROOM_NOT_FOUND',
          '객실을 찾을 수 없습니다.'
        );
      }

      if (action === 'ASSIGN_ROOMMAID') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '룸메이드 배정 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const primaryEmployeeNo = cleanText_(body.employeeNo, 80);
        const rawSecondaryEmployeeNo = cleanText_(body.secondaryEmployeeNo, 80);
        const assignmentType = cleanText_(body.assignmentType || 'SOLO', 40).toUpperCase();
        const cleaningType = cleanText_(body.cleaningType || 'NORMAL', 40).toUpperCase();
        const pairAssignment = ['PAIR', 'PAIR_TRAINING'].includes(assignmentType);
        const secondaryEmployeeNo = pairAssignment ? rawSecondaryEmployeeNo : '';

        if (!primaryEmployeeNo) {
          throw httpError(400, 'ROOMMAID_REQUIRED', '주담당 룸메이드를 선택하세요.');
        }
        if (!['SOLO', 'PAIR', 'PAIR_TRAINING'].includes(assignmentType)) {
          throw httpError(400, 'INVALID_ASSIGNMENT_TYPE', '지원하지 않는 룸메이드 배정유형입니다.');
        }
        if (pairAssignment && !secondaryEmployeeNo) {
          throw httpError(400, 'SECONDARY_ROOMMAID_REQUIRED', '보조 룸메이드를 선택하세요.');
        }
        if (secondaryEmployeeNo && primaryEmployeeNo === secondaryEmployeeNo) {
          throw httpError(400, 'DUPLICATE_ROOMMAID', '주담당과 보조 룸메이드는 서로 달라야 합니다.');
        }

        const employeeNos = pairAssignment
          ? [primaryEmployeeNo, secondaryEmployeeNo]
          : [primaryEmployeeNo];
        const staffResult = await client.query(
          `select employee_no,name,role,enabled
             from public.nova_users
            where employee_no = any($1::text[])`,
          [employeeNos]
        );
        const staffByNo = Object.fromEntries(
          staffResult.rows.map(item => [String(item.employee_no || ''), item])
        );
        const primaryUser = staffByNo[primaryEmployeeNo] || null;
        const secondaryUser = secondaryEmployeeNo ? (staffByNo[secondaryEmployeeNo] || null) : null;

        if (!primaryUser || !primaryUser.enabled || String(primaryUser.role || '').toUpperCase() !== 'ROOMMAID') {
          throw httpError(400, 'ROOMMAID_NOT_AVAILABLE', '주담당 룸메이드 정보를 확인할 수 없습니다.');
        }
        if (pairAssignment && (!secondaryUser || !secondaryUser.enabled || String(secondaryUser.role || '').toUpperCase() !== 'ROOMMAID')) {
          throw httpError(400, 'ROOMMAID_NOT_AVAILABLE', '보조 룸메이드 정보를 확인할 수 없습니다.');
        }

        const sameAssignment = String(room.cleaning_status || '').toUpperCase() === 'ASSIGNED'
          && String(room.cleaning_type || 'NORMAL').toUpperCase() === cleaningType
          && String(room.assignment_type || 'SOLO').toUpperCase() === assignmentType
          && String(room.roommaid_employee_no || '') === primaryEmployeeNo
          && String(room.secondary_roommaid_employee_no || '') === secondaryEmployeeNo;

        if (sameAssignment) {
          const response = {
            ok: true,
            action,
            requestId,
            idempotent: true,
            room: roomDto(room),
            version: Number(room.version || 0),
            timing: { totalMs: Date.now() - startedAt }
          };
          await client.query(
            `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
            [requestId, JSON.stringify(response)]
          );
          await client.query('commit');
          return res.json(response);
        }

        const before = String(room.cleaning_status || '');
        const updated = await client.query(
          `update public.nova_rooms_current
              set cleaning_status='ASSIGNED',
                  cleaning_type=$4,
                  assignment_type=$5,
                  roommaid_employee_no=$6,
                  secondary_roommaid_employee_no=nullif($7,''),
                  version=version+1,
                  updated_by=$8,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [
            businessDate,
            site,
            roomNo,
            cleaningType,
            assignmentType,
            primaryEmployeeNo,
            secondaryEmployeeNo,
            user.employee_no
          ]
        );
        const nextRoom = updated.rows[0];

        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          cleaningType,
          assignmentType,
          primaryEmployeeNo,
          primaryName: String(primaryUser.name || ''),
          secondaryEmployeeNo,
          secondaryName: secondaryUser ? String(secondaryUser.name || '') : ''
        };

        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            'ASSIGNED',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
          ok: true,
          action,
          requestId,
          room: roomDto(nextRoom),
          version: Number(nextRoom.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }


      if (action === 'UPDATE_ROOM_OPERATION_STATUS') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '객실 조치상태 변경 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const rawOperationalStatus = cleanText_(body.operationalStatus, 40).toUpperCase();
        const operationalStatus = rawOperationalStatus === ''
          ? ''
          : (['BROKEN', 'OUT_OF_ORDER', 'OOO', 'O.O.O', '0.0.0'].includes(rawOperationalStatus)
              ? 'BROKEN'
              : (['ROOM_CHECK', 'ROOMCHECK', 'CHECK_ROOM'].includes(rawOperationalStatus)
                  ? 'ROOM_CHECK'
                  : ''));
        if (rawOperationalStatus && !operationalStatus) {
          throw httpError(400, 'INVALID_OPERATIONAL_STATUS', '사용할 수 없는 객실 조치상태입니다.');
        }

        const previousOperationalStatus = String(room.operational_status || '').trim().toUpperCase();
        if (previousOperationalStatus === operationalStatus) {
          const response = {
            ok: true,
            action,
            requestId,
            idempotent: true,
            room: roomDto(room),
            version: Number(room.version || 0),
            timing: { totalMs: Date.now() - startedAt }
          };
          await client.query(
            `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
            [requestId, JSON.stringify(response)]
          );
          await client.query('commit');
          return res.json(response);
        }

        const updated = await client.query(
          `update public.nova_rooms_current
              set operational_status=nullif($4,''),
                  version=version+1,
                  updated_by=$5,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [businessDate, site, roomNo, operationalStatus, user.employee_no]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          previousOperationalStatus,
          operationalStatus
        };

        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            previousOperationalStatus,
            operationalStatus,
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
          ok: true,
          action,
          requestId,
          room: roomDto(nextRoom),
          version: Number(nextRoom.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }

      if (action === 'CHANGE_ROOM_STATUS') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', '객실상태 변경 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const requestedRoomStatus = cleanText_(body.roomStatus, 40).toUpperCase();
        if (!requestedRoomStatus) {
          throw httpError(400, 'ROOM_STATUS_REQUIRED', '변경할 객실상태를 선택하세요.');
        }
        if (requestedRoomStatus === 'CHECKED_OUT') {
          throw httpError(400, 'CHECKOUT_LEGACY_ONLY', '퇴실은 기존 전용 저장경로를 사용합니다.');
        }

        const rawPatch = body.realtimeRoomPatch && typeof body.realtimeRoomPatch === 'object'
          ? body.realtimeRoomPatch
          : {};
        const hasOwn = key => Object.prototype.hasOwnProperty.call(rawPatch, key);
        const cleaningStatus = hasOwn('cleaningStatus')
          ? cleanText_(rawPatch.cleaningStatus || 'WAITING', 40).toUpperCase()
          : String(room.cleaning_status || 'WAITING').toUpperCase();
        const cleaningType = hasOwn('cleaningType')
          ? cleanText_(rawPatch.cleaningType || 'NORMAL', 40).toUpperCase()
          : String(room.cleaning_type || 'NORMAL').toUpperCase();
        const assignmentType = hasOwn('assignmentType')
          ? cleanText_(rawPatch.assignmentType || 'SOLO', 40).toUpperCase()
          : String(room.assignment_type || 'SOLO').toUpperCase();
        const roommaidEmployeeNo = hasOwn('roommaidEmployeeNo')
          ? cleanText_(rawPatch.roommaidEmployeeNo, 80)
          : String(room.roommaid_employee_no || '');
        const secondaryRoommaidEmployeeNo = hasOwn('secondaryRoommaidEmployeeNo')
          ? cleanText_(rawPatch.secondaryRoommaidEmployeeNo, 80)
          : String(room.secondary_roommaid_employee_no || '');
        const qmEmployeeNo = hasOwn('qmEmployeeNo')
          ? cleanText_(rawPatch.qmEmployeeNo, 80)
          : String(room.qm_employee_no || '');

        const roomPatch = {
          cleaningStatus,
          cleaningType,
          assignmentType,
          roommaidEmployeeNo,
          secondaryRoommaidEmployeeNo,
          qmEmployeeNo
        };

        const sameState = String(room.room_status || '').toUpperCase() === requestedRoomStatus
          && String(room.cleaning_status || 'WAITING').toUpperCase() === cleaningStatus
          && String(room.cleaning_type || 'NORMAL').toUpperCase() === cleaningType
          && String(room.assignment_type || 'SOLO').toUpperCase() === assignmentType
          && String(room.roommaid_employee_no || '') === roommaidEmployeeNo
          && String(room.secondary_roommaid_employee_no || '') === secondaryRoommaidEmployeeNo
          && String(room.qm_employee_no || '') === qmEmployeeNo;

        if (sameState) {
          const response = {
            ok: true,
            action,
            requestId,
            idempotent: true,
            room: roomDto(room),
            version: Number(room.version || 0),
            timing: { totalMs: Date.now() - startedAt }
          };
          await client.query(
            `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
            [requestId, JSON.stringify(response)]
          );
          await client.query('commit');
          return res.json(response);
        }

        const previousRoomStatus = String(room.room_status || '');
        const updated = await client.query(
          `update public.nova_rooms_current
              set room_status=$4,
                  cleaning_status=$5,
                  cleaning_type=$6,
                  assignment_type=$7,
                  roommaid_employee_no=nullif($8,''),
                  secondary_roommaid_employee_no=nullif($9,''),
                  qm_employee_no=nullif($10,''),
                  version=version+1,
                  updated_by=$11,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [
            businessDate,
            site,
            roomNo,
            requestedRoomStatus,
            cleaningStatus,
            cleaningType,
            assignmentType,
            roommaidEmployeeNo,
            secondaryRoommaidEmployeeNo,
            qmEmployeeNo,
            user.employee_no
          ]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          roomStatus: requestedRoomStatus,
          roomPatch
        };

        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            previousRoomStatus,
            requestedRoomStatus,
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
          ok: true,
          action,
          requestId,
          room: roomDto(nextRoom),
          version: Number(nextRoom.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }

      if (action === 'QM_ASSIGN') {
        if (!['ADMIN', 'ORDER'].includes(user.role)) {
          throw httpError(403, 'FORBIDDEN', 'QM 배정 권한이 없습니다.');
        }

        if (expectedVersion > 0 && expectedVersion !== Number(room.version)) {
          throw httpError(409, 'VERSION_CONFLICT', '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.', {
            currentRoom: roomDto(room)
          });
        }

        const qmEmployeeNo = cleanText_(body.employeeNo, 80);
        if (!qmEmployeeNo) {
          throw httpError(400, 'QM_REQUIRED', '배정할 QM을 선택하세요.');
        }

        const qmResult = await client.query(
          `select employee_no,name,role,enabled
             from public.nova_users
            where employee_no=$1`,
          [qmEmployeeNo]
        );
        const qmUser = qmResult.rows[0] || null;
        if (!qmUser || !qmUser.enabled || String(qmUser.role || '').toUpperCase() !== 'QM') {
          throw httpError(400, 'QM_NOT_AVAILABLE', '배정할 QM 정보를 확인할 수 없습니다.');
        }

        const sameAssignment = String(room.cleaning_status || '').toUpperCase() === 'QM_WAITING'
          && String(room.qm_employee_no || '') === qmEmployeeNo;
        if (sameAssignment) {
          const response = {
            ok: true,
            action,
            requestId,
            idempotent: true,
            room: roomDto(room),
            version: Number(room.version || 0),
            timing: { totalMs: Date.now() - startedAt }
          };
          await client.query(
            `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
            [requestId, JSON.stringify(response)]
          );
          await client.query('commit');
          return res.json(response);
        }

        const before = String(room.cleaning_status || '');
        const updated = await client.query(
          `update public.nova_rooms_current
              set cleaning_status='QM_WAITING',
                  qm_employee_no=$4,
                  version=version+1,
                  updated_by=$5,
                  updated_at=now()
            where business_date=$1 and site=$2 and room_no=$3
            returning *`,
          [businessDate, site, roomNo, qmEmployeeNo, user.employee_no]
        );
        const nextRoom = updated.rows[0];
        const detail = {
          source: 'NOVA_REALTIME',
          role: user.role,
          qmEmployeeNo,
          qmName: String(qmUser.name || '')
        };

        await client.query(
          `insert into public.nova_room_events(
            request_id,business_date,site,room_no,action,before_status,after_status,
            employee_no,room_version,detail
          ) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)`,
          [
            requestId,
            businessDate,
            site,
            roomNo,
            action,
            before,
            'QM_WAITING',
            user.employee_no,
            nextRoom.version,
            JSON.stringify(detail)
          ]
        );

        const response = {
          ok: true,
          action,
          requestId,
          room: roomDto(nextRoom),
          version: Number(nextRoom.version || 0),
          timing: { totalMs: Date.now() - startedAt }
        };
        await client.query(
          `update public.nova_request_dedup set response_json=$2::jsonb where request_id=$1`,
          [requestId, JSON.stringify(response)]
        );
        await client.query('commit');
        return res.json(response);
      }


      if (
        !canCleanRoom(
          user,
          room
        )
      ) {
        throw httpError(
          403,
          'FORBIDDEN',
          '이 객실의 청소 처리 권한이 없습니다.'
        );
      }

      const hasQmHint =
        Object.prototype.hasOwnProperty.call(
          body,
          'qmEmployeeNo'
        );

      const qmEmployeeNo =
        hasQmHint
          ? cleanText_(
              body.qmEmployeeNo,
              80
            )
          : String(
              room.qm_employee_no || ''
            );

      const target =
        action === 'CLEANING_START'
          ? 'CLEANING'
          : (
              qmEmployeeNo
                ? 'QM_WAITING'
                : 'COMPLETED'
            );

      if (
        room.cleaning_status === target
      ) {

        const response = {
          ok: true,
          action,
          requestId,
          idempotent: true,
          alreadyCompleted:
            action ===
            'CLEANING_COMPLETE',
          room:
            roomDto(room),
          version:
            Number(
              room.version || 0
            ),
          timing: {
            totalMs:
              Date.now() - startedAt
          }
        };

        await client.query(
          `
          update public.nova_request_dedup
          set response_json=$2::jsonb
          where request_id=$1
          `,
          [
            requestId,
            JSON.stringify(response)
          ]
        );

        await client.query('commit');

        return res.json(response);
      }

      if (
        expectedVersion > 0
        && expectedVersion
          !== Number(room.version)
      ) {

        throw httpError(
          409,
          'VERSION_CONFLICT',
          '객실 정보가 다른 사용자에 의해 먼저 변경되었습니다.',
          {
            currentRoom:
              roomDto(room)
          }
        );
      }

      if (
        action === 'CLEANING_START'
        && ![
          'ASSIGNED',
          'WAITING',
          'REWORK'
        ].includes(
          room.cleaning_status
        )
      ) {

        throw httpError(
          409,
          'INVALID_STATE',
          `현재 ${room.cleaning_status} 상태에서는 청소시작할 수 없습니다.`
        );
      }

      if (
        action === 'CLEANING_COMPLETE'
        && room.cleaning_status
          !== 'CLEANING'
      ) {

        throw httpError(
          409,
          'INVALID_STATE',
          `현재 ${room.cleaning_status} 상태에서는 청소완료할 수 없습니다.`
        );
      }

      const before =
        room.cleaning_status;

      const updated =
        await client.query(
          `
          update public.nova_rooms_current

          set
            cleaning_status=$4,
            version=version+1,

            cleaning_started_at=
              case
                when $4='CLEANING'
                  then coalesce(
                    cleaning_started_at,
                    now()
                  )
                else cleaning_started_at
              end,

            cleaning_completed_at=
              case
                when $4 in (
                  'COMPLETED',
                  'QM_WAITING'
                )
                  then now()
                else cleaning_completed_at
              end,

            updated_by=$5,

            qm_employee_no=
              case
                when $6::boolean
                  then nullif($7,'')
                else qm_employee_no
              end,

            updated_at=now()

          where
            business_date=$1
            and site=$2
            and room_no=$3

          returning *
          `,
          [
            businessDate,
            site,
            roomNo,
            target,
            user.employee_no,
            hasQmHint,
            qmEmployeeNo
          ]
        );

      const nextRoom =
        updated.rows[0];

      await client.query(
        `
        insert into public.nova_room_events(
          request_id,
          business_date,
          site,
          room_no,
          action,
          before_status,
          after_status,
          employee_no,
          room_version,
          detail
        )
        values(
          $1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb
        )
        `,
        [
          requestId,
          businessDate,
          site,
          roomNo,
          action,
          before,
          target,
          user.employee_no,
          nextRoom.version,
          JSON.stringify({
            source:
              'NOVA_REALTIME',
            role:
              user.role
          })
        ]
      );

      const response = {
        ok: true,
        action,
        requestId,
        room:
          roomDto(nextRoom),
        version:
          Number(
            nextRoom.version || 0
          ),
        timing: {
          totalMs:
            Date.now() - startedAt
        }
      };

      await client.query(
        `
        update public.nova_request_dedup
        set response_json=$2::jsonb
        where request_id=$1
        `,
        [
          requestId,
          JSON.stringify(response)
        ]
      );

      await client.query('commit');

      res.json(response);

    } catch (e) {

      if (client) {
        try {
          await client.query('rollback');
        } catch {}
      }

      next(e);

    } finally {

      if (client) {
        client.release();
      }
    }
  }
);

/**
 * 하우스맨 오더 Realtime 선등록.
 *
 * 기존 Sheet 오더 / 감사이력 / Telegram은
 * Apps Script 백그라운드 미러가 계속 담당.
 *
 * 이 API는 PostgreSQL 등록 확정과
 * 관리자간 즉시 전파를 빠르게 처리.
 */
app.post(
  '/v1/houseman-orders',
  async (req, res, next) => {

    const startedAt =
      Date.now();

    let client;

    try {
      client =
        await pool.connect();

      const auth =
        authBearer(req);

      const body =
        req.body || {};

      const businessDate =
        cleanText_(
          body.businessDate,
          20
        );

      const site =
        cleanText_(
          body.site,
          80
        );

      const roomNo =
        cleanText_(
          body.roomNo,
          40
        );

      const part =
        cleanText_(
          body.part,
          80
        );

      const requester =
        cleanText_(
          body.requester
          || '오더테이커',
          120
        );

      const note =
        String(
          body.note || ''
        ).trim().slice(
          0,
          4000
        );

      const assignmentMode =
        cleanText_(
          body.assignmentMode
          || 'UNASSIGNED',
          20
        ).toUpperCase();

      const orderId =
        cleanText_(
          body.orderId,
          80
        ).toUpperCase();

      const requestId =
        cleanText_(
          body.requestId
          || req.headers['x-request-id'],
          200
        );

      const items =
        normalizeHousemanItems_(
          body.items
        );

      const important =
        body.important === true
        || String(
          body.important || ''
        ).toUpperCase() === 'Y';

      const handover =
        body.handover === true
        || String(
          body.handover || ''
        ).toUpperCase() === 'Y';

      const assignment =
        body.assignment
        && typeof body.assignment
          === 'object'
          ? body.assignment
          : {};

      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(
          businessDate
        )
        || !site
        || !roomNo
        || !part
        || !items.length
        || !requestId
      ) {

        throw httpError(
          400,
          'INVALID_REQUEST',
          '업무일자·사업장·객실번호·파트·품목·requestId가 필요합니다.'
        );
      }

      if (
        !/^HO-\d{8}-[A-Z0-9]{8,32}$/.test(
          orderId
        )
      ) {

        throw httpError(
          400,
          'INVALID_ORDER_ID',
          '오더 번호 형식이 올바르지 않습니다.'
        );
      }

      if (
        ![
          'AUTO',
          'UNASSIGNED',
          'MANUAL'
        ].includes(
          assignmentMode
        )
      ) {

        throw httpError(
          400,
          'INVALID_ASSIGNMENT_MODE',
          '지원하지 않는 하우스맨 배정방식입니다.'
        );
      }

      await client.query('begin');

      const user =
        await loadUser(
          client,
          auth.employeeNo
        );

      if (
        ![
          'ADMIN',
          'ORDER'
        ].includes(
          user.role
        )
      ) {

        throw httpError(
          403,
          'FORBIDDEN',
          '하우스맨 오더 등록 권한이 없습니다.'
        );
      }

      if (
        !allowedForSite(
          user,
          site
        )
      ) {

        throw httpError(
          403,
          'FORBIDDEN',
          '해당 사업장 처리 권한이 없습니다.'
        );
      }

      const insertedRequest =
        await client.query(
          `
          insert into public.nova_request_dedup(
            request_id,
            employee_no,
            action
          )
          values(
            $1,
            $2,
            'HOUSEMAN_CREATE'
          )
          on conflict(request_id)
          do nothing
          returning request_id
          `,
          [
            requestId,
            user.employee_no
          ]
        );

      if (!insertedRequest.rowCount) {

        const prior =
          await client.query(
            `
            select response_json
            from public.nova_request_dedup
            where request_id=$1
            `,
            [requestId]
          );

        await client.query('commit');

        if (
          prior.rows[0]?.response_json
        ) {

          return res.json({
            ...prior.rows[0].response_json,
            duplicateRequest: true
          });
        }

        throw httpError(
          409,
          'REQUEST_IN_PROGRESS',
          '동일 요청이 처리 중입니다.'
        );
      }

      let assignedEmployeeNo = '';
      let assignedName = '';

      let candidateEmployeeNos = [];
      let candidateNames = [];

      let routeLocked = true;
      let autoAssigned = false;

      const assignedBuilding =
        cleanText_(
          assignment.building
          || `${String(roomNo).charAt(0)}동`,
          40
        );

      const currentShiftRaw =
        cleanText_(
          assignment.currentShift,
          10
        ).toUpperCase();

      const assignedShiftCode =
        ['A', 'B', 'C'].includes(
          currentShiftRaw
        )
          ? currentShiftRaw
          : '';

      const assignedShiftCodes =
        normalizeShiftCodes_(
          assignment.activeShiftCodes
        );

      const handoverShiftRaw =
        cleanText_(
          body.handoverTargetShift,
          10
        ).toUpperCase();

      const handoverTargetShift =
        ['A', 'B', 'C'].includes(
          handoverShiftRaw
        )
          ? handoverShiftRaw
          : '';

      if (
        assignmentMode === 'AUTO'
      ) {

        candidateEmployeeNos =
          Array.from(
            new Set(
              (
                Array.isArray(
                  assignment.employeeNos
                )
                  ? assignment.employeeNos
                  : []
              )
                .map(value =>
                  cleanText_(value, 80)
                )
                .filter(Boolean)
            )
          );

        assignedEmployeeNo =
          cleanText_(
            assignment.employeeNo
            || candidateEmployeeNos[0],
            80
          );

        if (
          !assignedEmployeeNo
          || !candidateEmployeeNos
              .includes(
                assignedEmployeeNo
              )
        ) {

          throw httpError(
            409,
            'HOUSEMAN_ASSIGNMENT_REQUIRED',
            '담당 하우스맨 정보를 다시 확인하세요.'
          );
        }

        const { rows } =
          await client.query(
            `
            select
              employee_no,
              name,
              role,
              enabled
            from public.nova_users
            where
              employee_no =
              any($1::text[])
            `,
            [
              candidateEmployeeNos
            ]
          );

        const byEmployeeNo =
          new Map(
            rows.map(row => [
              String(row.employee_no),
              row
            ])
          );

        candidateNames =
          candidateEmployeeNos.map(
            employeeNo => {

              const candidate =
                byEmployeeNo.get(
                  employeeNo
                );

              if (
                !candidate
                || candidate.enabled !== true
                || String(
                  candidate.role
                ).toUpperCase()
                  !== 'HOUSEMAN'
              ) {

                throw httpError(
                  409,
                  'HOUSEMAN_NOT_AVAILABLE',
                  '사용 가능한 하우스맨 계정이 아닙니다.'
                );
              }

              return String(
                candidate.name
                || employeeNo
              );
            }
          );

        assignedName =
          candidateNames[
            candidateEmployeeNos
              .indexOf(
                assignedEmployeeNo
              )
          ]
          || assignedEmployeeNo;

        routeLocked = false;
        autoAssigned = true;

      } else if (
        assignmentMode === 'MANUAL'
      ) {

        assignedEmployeeNo =
          cleanText_(
            body.assignedEmployeeNo
            || assignment.employeeNo,
            80
          );

        if (!assignedEmployeeNo) {

          throw httpError(
            400,
            'HOUSEMAN_ASSIGNMENT_REQUIRED',
            '배정 직원을 선택하세요.'
          );
        }

        const { rows } =
          await client.query(
            `
            select
              employee_no,
              name,
              role,
              enabled
            from public.nova_users
            where employee_no=$1
            limit 1
            `,
            [
              assignedEmployeeNo
            ]
          );

        const candidate =
          rows[0];

        if (
          !candidate
          || candidate.enabled !== true
          || String(
            candidate.role
          ).toUpperCase()
            !== 'HOUSEMAN'
        ) {

          throw httpError(
            409,
            'HOUSEMAN_NOT_AVAILABLE',
            '사용 가능한 하우스맨 계정이 아닙니다.'
          );
        }

        assignedName =
          String(
            candidate.name
            || assignedEmployeeNo
          );

        candidateEmployeeNos =
          [assignedEmployeeNo];

        candidateNames =
          [assignedName];
      }

      const statusCode =
        assignedEmployeeNo
          ? 'ASSIGNED'
          : 'REGISTERED';

      const itemSummary =
        items
          .map(item =>
            item.quantity > 1
              ? `${item.name}×${item.quantity}`
              : item.name
          )
          .join(', ');

      const quantity =
        items.reduce(
          (sum, item) =>
            sum + item.quantity,
          0
        );

      const insertedOrder =
        await client.query(
          `
          insert into public.nova_houseman_orders(
            order_id,
            business_date,
            site,
            room_no,
            part,
            items,
            item_summary,
            quantity,
            note,
            requester,

            assigned_employee_no,
            assigned_name,
            status_code,

            important,
            handover,
            handover_target_shift,

            assignment_mode,
            auto_assigned,
            assigned_building,
            assigned_shift_code,
            assigned_shift_codes,

            route_candidate_employee_nos,
            route_candidate_names,
            route_locked,

            registered_by
          )
          values(
            $1,
            $2::date,
            $3,
            $4,
            $5,
            $6::jsonb,
            $7,
            $8,
            $9,
            $10,

            nullif($11,''),
            $12,
            $13,

            $14,
            $15,
            $16,

            $17,
            $18,
            $19,
            $20,
            $21::text[],

            $22::text[],
            $23::text[],
            $24,

            $25
          )
          on conflict(order_id)
          do nothing
          returning *
          `,
          [
            orderId,
            businessDate,
            site,
            roomNo,
            part,

            JSON.stringify(items),
            itemSummary,
            quantity,
            note,
            requester,

            assignedEmployeeNo,
            assignedName,
            statusCode,

            important,
            handover,
            handoverTargetShift,

            assignmentMode,
            autoAssigned,
            assignedBuilding,
            assignedShiftCode,
            assignedShiftCodes,

            candidateEmployeeNos,
            candidateNames,
            routeLocked,

            user.employee_no
          ]
        );

      let orderRow =
        insertedOrder.rows[0];

      let idempotent = false;

      if (!orderRow) {

        const existing =
          await client.query(
            `
            select *
            from public.nova_houseman_orders
            where order_id=$1
            limit 1
            `,
            [orderId]
          );

        orderRow =
          existing.rows[0];

        if (!orderRow) {

          throw httpError(
            409,
            'ORDER_ID_CONFLICT',
            '오더 번호 충돌이 발생했습니다.'
          );
        }

        idempotent = true;
      }

      const response = {
        ok: true,
        action:
          'HOUSEMAN_CREATE',
        requestId,
        order:
          housemanOrderDto_(
            orderRow
          ),
        orderVersion:
          Number(
            orderRow.version || 0
          ),
        idempotent,
        timing: {
          totalMs:
            Date.now() - startedAt
        }
      };

      await client.query(
        `
        update public.nova_request_dedup

        set response_json=$2::jsonb

        where request_id=$1
        `,
        [
          requestId,
          JSON.stringify(response)
        ]
      );

      await client.query('commit');

      res.json(response);

    } catch (e) {

      if (client) {
        try {
          await client.query('rollback');
        } catch {}
      }

      next(e);

    } finally {

      if (client) {
        client.release();
      }
    }
  }
);

app.post(
  '/v1/auth/realtime-token',
  async (req, res, next) => {

    let client;

    try {
      client =
        await pool.connect();

      if (
        !SUPABASE_URL
        || !SUPABASE_PUBLISHABLE_KEY
        || !SUPABASE_JWT_SECRET
      ) {

        throw httpError(
          503,
          'REALTIME_NOT_CONFIGURED',
          'Realtime 환경설정이 완료되지 않았습니다.'
        );
      }

      const auth =
        authBearer(req);

      const user =
        await loadUser(
          client,
          auth.employeeNo
        );

      let sites =
        Array.from(
          new Set(
            [
              ...(user.allowed_sites || []),
              user.default_site
            ].filter(Boolean)
          )
        );

      if (
        ['ADMIN', 'ORDER'].includes(
          user.role
        )
      ) {

        const { rows } =
          await client.query(`
            select distinct site
            from public.nova_rooms_current
            where
              site is not null
              and site<>''
            order by site
          `);

        sites =
          rows
            .map(row => row.site)
            .filter(Boolean);
      }

      const now =
        Math.floor(
          Date.now() / 1000
        );

      const token =
        jwt.sign(
          {
            aud: 'authenticated',
            role: 'authenticated',
            sub:
              String(
                user.employee_no
              ),
            employee_no:
              String(
                user.employee_no
              ),
            nova_role:
              user.role,
            sites,
            iat: now
          },
          SUPABASE_JWT_SECRET,
          {
            algorithm: 'HS256',
            expiresIn: '15m',
            issuer:
              'nova-realtime'
          }
        );

      res.json({
        ok: true,
        token,
        expiresIn: 900,
        supabaseUrl:
          SUPABASE_URL,
        publishableKey:
          SUPABASE_PUBLISHABLE_KEY,
        sites
      });

    } catch (e) {
      next(e);

    } finally {

      if (client) {
        client.release();
      }
    }
  }
);

app.use(
  (err, _req, res, _next) => {

    const status =
      Number(
        err.status || 500
      );

    if (status >= 500) {
      console.error(err);
    }

    const body = {
      ok: false,
      code:
        err.code
        || 'INTERNAL_ERROR',
      message:
        status >= 500
          ? '서버 처리 중 오류가 발생했습니다.'
          : err.message
    };

    if (err.currentRoom) {
      body.currentRoom =
        err.currentRoom;
    }

    res
      .status(status)
      .json(body);
  }
);

app.listen(
  PORT,
  '0.0.0.0',
  () => {
    console.log(
      `NOVA Realtime API :${PORT}`
    );
  }
);