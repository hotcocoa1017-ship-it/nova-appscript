import fs from 'node:fs';
import { createClient } from '@supabase/supabase-js';

const configPath = process.env.NOVA_REALTIME_CONFIG_FILE || '';
const token = String(process.env.NOVA_REALTIME_TOKEN || '').trim();
const site = String(process.env.NOVA_REALTIME_SITE || '').trim();
const timeoutMs = Math.max(2000, Number(process.env.NOVA_REALTIME_TIMEOUT_MS || 10000));

if (!configPath || !token || !site) {
  throw new Error('Realtime smoke inputs are incomplete');
}

const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
if (config?.ok !== true
    || typeof config.supabaseUrl !== 'string'
    || !config.supabaseUrl.trim()
    || typeof config.publishableKey !== 'string'
    || !config.publishableKey.trim()
    || config.privateChannel !== true
    || config.topicPattern !== 'nova:site:{site}:rooms') {
  throw new Error('Realtime bootstrap response is invalid');
}

const client = createClient(config.supabaseUrl, config.publishableKey, {
  auth: {
    persistSession: false,
    autoRefreshToken: false,
    detectSessionInUrl: false,
  },
});

await client.realtime.setAuth(token);
const topic = config.topicPattern.replace('{site}', site);
const channel = client.channel(topic, { config: { private: true } });

try {
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('private Realtime subscription timed out')), timeoutMs);
    channel.subscribe((status) => {
      if (status === 'SUBSCRIBED') {
        clearTimeout(timer);
        resolve();
        return;
      }
      if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
        clearTimeout(timer);
        reject(new Error(`private Realtime subscription failed: ${status}`));
      }
    });
  });
  process.stdout.write('CORE3_PRIVATE_REALTIME_SUBSCRIPTION=OK\n');
} finally {
  try {
    await client.removeChannel(channel);
  } catch (_) {}
  try {
    await client.realtime.disconnect();
  } catch (_) {}
}
