const fs = require('fs');

const repoConfig = JSON.parse(fs.readFileSync('.clasp.json', 'utf8'));
const scriptId = String(repoConfig.scriptId || '').trim();
if (!scriptId) throw new Error('Missing scriptId in .clasp.json');

const authPath = `${process.env.HOME}/.clasprc.json`;
const authConfig = JSON.parse(fs.readFileSync(authPath, 'utf8'));

function findFirst(obj, keys) {
  if (!obj || typeof obj !== 'object') return '';
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, key) && obj[key]) return String(obj[key]);
  }
  for (const value of Object.values(obj)) {
    if (value && typeof value === 'object') {
      const found = findFirst(value, keys);
      if (found) return found;
    }
  }
  return '';
}

let accessToken = findFirst(authConfig, ['access_token', 'accessToken']);
const refreshToken = findFirst(authConfig, ['refresh_token', 'refreshToken']);
const clientId = findFirst(authConfig, ['clientId', 'client_id']);
const clientSecret = findFirst(authConfig, ['clientSecret', 'client_secret']);

async function refreshAccessToken() {
  if (!refreshToken || !clientId || !clientSecret) {
    throw new Error('Could not resolve OAuth refresh credentials from .clasprc.json');
  }
  const body = new URLSearchParams({
    client_id: clientId,
    client_secret: clientSecret,
    refresh_token: refreshToken,
    grant_type: 'refresh_token'
  });
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.access_token) {
    throw new Error(`OAuth token refresh failed (${response.status})`);
  }
  accessToken = String(data.access_token);
}

async function api(path, options = {}, retried = false) {
  if (!accessToken) await refreshAccessToken();
  const response = await fetch(`https://script.googleapis.com/v1/${path}`, {
    method: options.method || 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  if (response.status === 401 && !retried) {
    await refreshAccessToken();
    return api(path, options, true);
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(`Apps Script API ${options.method || 'GET'} ${path} failed (${response.status}): ${data?.error?.message || text}`);
  }
  return data;
}

async function listAll(path, field) {
  const rows = [];
  let pageToken = '';
  do {
    const query = new URLSearchParams({ pageSize: '50' });
    if (pageToken) query.set('pageToken', pageToken);
    const data = await api(`${path}?${query.toString()}`);
    rows.push(...(Array.isArray(data[field]) ? data[field] : []));
    pageToken = String(data.nextPageToken || '');
  } while (pageToken);
  return rows;
}

(async () => {
  const versions = await listAll(`projects/${encodeURIComponent(scriptId)}/versions`, 'versions');
  const deployments = await listAll(`projects/${encodeURIComponent(scriptId)}/deployments`, 'deployments');
  const referenced = new Set(
    deployments
      .map(item => Number(item?.deploymentConfig?.versionNumber || 0))
      .filter(Number.isFinite)
      .filter(value => value > 0)
  );

  const total = versions.length;
  const targetTotal = 190;
  if (total < 195) {
    console.log(`Apps Script versions: ${total}. Pruning not required.`);
    if (process.env.GITHUB_OUTPUT) fs.appendFileSync(process.env.GITHUB_OUTPUT, 'pruned=false\n');
    return;
  }

  const candidates = versions
    .map(item => ({
      versionNumber: Number(item.versionNumber || 0),
      createTime: String(item.createTime || '')
    }))
    .filter(item => item.versionNumber > 0 && !referenced.has(item.versionNumber))
    .sort((a, b) => a.versionNumber - b.versionNumber);

  const deleteCount = Math.max(0, total - targetTotal);
  if (candidates.length < deleteCount) {
    throw new Error(`Not enough unused versions to prune safely. Need ${deleteCount}, found ${candidates.length}.`);
  }

  const selected = candidates.slice(0, deleteCount);
  for (const item of selected) {
    await api(`projects/${encodeURIComponent(scriptId)}/versions/${item.versionNumber}`, { method: 'DELETE' });
    console.log(`Deleted unused Apps Script version ${item.versionNumber}.`);
  }

  console.log(`Apps Script version count reduced from ${total} to approximately ${total - selected.length}.`);
  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `pruned=${selected.length > 0 ? 'true' : 'false'}\n`);
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `deleted_count=${selected.length}\n`);
  }
})().catch(error => {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
