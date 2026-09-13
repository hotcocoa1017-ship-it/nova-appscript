/**
 * Database Seed Runner
 * Executes sql/002_seed_initial_data.sql against PostgreSQL / Supabase
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
  console.log('   실행 예: $env:DATABASE_URL="postgresql://..."; node scripts/db-seed.mjs');
  process.exit(1);
}

async function runSeed() {
  const client = new Client({
    connectionString,
    ssl: process.env.PG_SSL === 'false' ? false : { rejectUnauthorized: false }
  });

  try {
    console.log('🔌 Connecting to database...');
    await client.connect();
    console.log('✅ Connected successfully.');

    const sqlPath = path.join(__dirname, '..', 'sql', '002_seed_initial_data.sql');
    const sql = fs.readFileSync(sqlPath, 'utf8');

    console.log('🌱 Seeding initial rooms and staff accounts...');
    await client.query(sql);
    console.log('🎉 Database seeding finished successfully!');
  } catch (error) {
    console.error('❌ Seeding failed:', error);
    process.exit(1);
  } finally {
    await client.end();
  }
}

runSeed();
