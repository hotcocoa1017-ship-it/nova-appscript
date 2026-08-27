import http from 'http';
import pg from 'pg';

const { Pool } = pg;
const PORT = Number(process.env.PORT || 8080);
const DATABASE_URL = process.env.DATABASE_URL || '';
const PG_HOST = process.env.PG_HOST || '';
const PG_PORT = Number(process.env.PG_PORT || 6543);
const PG_USER = process.env.PG_USER || '';
const PG_PASSWORD = process.env.PG_PASSWORD || '';
const PG_DATABASE = process.env.PG_DATABASE || 'postgres';
const HAS_PG_PARTS = Boolean(PG_HOST && PG_USER && PG_PASSWORD && PG_DATABASE);

if (!DATABASE_URL && !HAS_PG_PARTS) {
  throw new Error('PostgreSQL connection settings are missing.');
}

const poolConfig = HAS_PG_PARTS
  ? {
      host: PG_HOST,
      port: PG_PORT,
      user: PG_USER,
      password: PG_PASSWORD,
      database: PG_DATABASE
    }
  : { connectionString: DATABASE_URL };

poolConfig.max = 2;
poolConfig.idleTimeoutMillis = 10000;
poolConfig.connectionTimeoutMillis = 10000;
poolConfig.ssl = process.env.PG_SSL === 'false'
  ? false
  : { rejectUnauthorized: false };

const pool = new Pool(poolConfig);

async function migrateEventTime_() {
  const client = await pool.connect();
  try {
    const columnsResult = await client.query(
      `select column_name
         from information_schema.columns
        where table_schema='public'
          and table_name='nova_room_events'`
    );
    const columns = new Set(columnsResult.rows.map(row => String(row.column_name || '')));
    if (!columns.size) {
      throw new Error('public.nova_room_events table was not found.');
    }

    const sourceColumn = columns.has('created_at')
      ? 'created_at'
      : (columns.has('updated_at') ? 'updated_at' : '');

    await client.query('begin');
    await client.query(
      'alter table public.nova_room_events add column if not exists event_time timestamptz'
    );

    if (sourceColumn) {
      await client.query(
        `update public.nova_room_events
            set event_time = ${sourceColumn}::timestamptz
          where event_time is null`
      );
    } else {
      await client.query(
        'update public.nova_room_events set event_time=now() where event_time is null'
      );
    }

    await client.query(
      'alter table public.nova_room_events alter column event_time set default now()'
    );
    await client.query(
      'alter table public.nova_room_events alter column event_time set not null'
    );
    await client.query('commit');

    await client.query(
      'create index if not exists idx_nova_room_events_cursor on public.nova_room_events(event_time, request_id)'
    );

    const verification = await client.query(
      `select
          count(*)::bigint as total_rows,
          count(*) filter (where event_time is null)::bigint as null_event_time_rows
         from public.nova_room_events`
    );
    const row = verification.rows[0] || {};
    if (Number(row.null_event_time_rows || 0) !== 0) {
      throw new Error('event_time verification failed.');
    }

    console.log(JSON.stringify({
      ok: true,
      migration: 'nova_room_events.event_time',
      sourceColumn: sourceColumn || 'now()',
      totalRows: Number(row.total_rows || 0),
      nullEventTimeRows: Number(row.null_event_time_rows || 0)
    }));
  } catch (error) {
    try {
      await client.query('rollback');
    } catch {}
    throw error;
  } finally {
    client.release();
  }
}

await migrateEventTime_();
await pool.end();

http.createServer((req, res) => {
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify({
    ok: true,
    migration: 'nova_room_events.event_time',
    path: req.url || '/'
  }));
}).listen(PORT, '0.0.0.0', () => {
  console.log(`NOVA event_time migration ready on :${PORT}`);
});
