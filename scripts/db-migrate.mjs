/**
 * Database Migration Runner
 * Executes sql/001_create_database.sql against PostgreSQL / Supabase
 */

import fs from 'fs';
import path from 'path';
import pg from 'pg';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const { Client } = pg;
const connectionString = process.env.DATABASE_URL;

if (!connectionString) {
  console.error('❌ Error: DATABASE_URL 환경변수가 설정되지 않았습니다.');
  console.log('   실행 예: $env:DATABASE_URL="postgresql://..."; node scripts/db-migrate.mjs');
  process.exit(1);
}

async function runMigration() {
  const client = new Client({
    connectionString,
    ssl: process.env.PG_SSL === 'false' ? false : { rejectUnauthorized: false }
  });

  try {
    console.log('🔌 Connecting to database...');
    await client.connect();
    console.log('✅ Connected successfully.');

    const sqlPath = path.join(__dirname, '..', 'sql', '001_create_database.sql');
    const sql = fs.readFileSync(sqlPath, 'utf8');

    console.log('🚀 Executing database migration schema (sql/001_create_database.sql)...');
    await client.query(sql);
    console.log('🎉 Migration completed successfully! Tables, indexes, triggers, and RLS policies created.');
  } catch (error) {
    console.error('❌ Migration failed:', error);
    process.exit(1);
  } finally {
    await client.end();
  }
}

runMigration();
