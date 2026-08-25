/**
 * NOVA Realtime 최초 데이터 이관 v3.2
 *
 * 목적:
 *   기존 Google Sheets의 사용자계정 / 현재객실현황을
 *   Cloud Run -> Supabase PostgreSQL로 최초 1회 안전하게 복사합니다.
 *
 * 주의:
 *   1) 기존 운영 NOVA가 아니라 새 복사본 프로젝트에만 추가합니다.
 *   2) NOVA_REALTIME_ENABLED는 반드시 N 상태에서 실행합니다.
 *   3) 이관 후에도 자동으로 Realtime을 켜지 않습니다.
 *   4) 실시간 처리 이력이 1건이라도 생기면 서버가 재이관을 자동 차단합니다.
 */

function runNovaRealtimeBootstrapMigration() { // (최초 사용자계정·현재객실현황 이관)
  const props = PropertiesService.getScriptProperties();
  const enabled = String(props.getProperty('NOVA_REALTIME_ENABLED') || 'N').trim().toUpperCase();
  if (enabled === 'Y') {
    throw new Error('Realtime이 활성화된 상태에서는 최초 이관을 실행할 수 없습니다. NOVA_REALTIME_ENABLED=N인지 확인하세요.');
  }

  const apiBase = String(props.getProperty('NOVA_REALTIME_API_BASE') || '').trim().replace(/\/+$/, '');
  const secret = String(props.getProperty('NOVA_TOKEN_SECRET') || '').trim();
  if (!apiBase) throw new Error('Script Properties의 NOVA_REALTIME_API_BASE가 비어 있습니다.');
  if (!secret) throw new Error('Script Properties의 NOVA_TOKEN_SECRET이 비어 있습니다.');

  const rooms = buildNovaRealtimeMigrationRooms_();
  const sites = Array.from(new Set(rooms.map(row => row.site).filter(Boolean))).sort();
  const users = buildNovaRealtimeMigrationUsers_(sites);

  if (!users.length) throw new Error('사용자계정 시트에서 이관할 계정을 찾지 못했습니다.');
  if (!rooms.length) throw new Error('현재객실현황 시트에서 이관할 객실을 찾지 못했습니다.');

  const body = JSON.stringify({
    source: 'GOOGLE_SHEETS_NOVA_COPY',
    generatedAt: new Date().toISOString(),
    users: users,
    rooms: rooms
  });

  const timestamp = String(Date.now());
  const signature = novaRealtimeMigrationHmacHex_(timestamp + '.' + body, secret);
  const response = UrlFetchApp.fetch(apiBase + '/v1/admin/bootstrap-import', {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    payload: body,
    headers: {
      'X-NOVA-Timestamp': timestamp,
      'X-NOVA-Signature': signature
    },
    muteHttpExceptions: true,
    followRedirects: true
  });

  const status = response.getResponseCode();
  const text = response.getContentText();
  let result = {};
  try { result = JSON.parse(text || '{}'); } catch (_) { result = { ok: false, message: text || '응답 해석 실패' }; }

  if (status < 200 || status >= 300 || !result.ok) {
    throw new Error('Realtime 최초 이관 실패 [' + status + '] ' + (result.message || result.code || text || '알 수 없는 오류'));
  }

  const summary = {
    ok: true,
    usersImported: Number(result.usersImported || 0),
    roomsImported: Number(result.roomsImported || 0),
    sites: result.sites || sites,
    importedAt: result.importedAt || '',
    message: '최초 데이터 이관이 완료되었습니다. 아직 NOVA_REALTIME_ENABLED는 N 상태입니다.'
  };
  console.log(JSON.stringify(summary, null, 2));
  return summary;
}

function previewNovaRealtimeBootstrapMigration() { // (DB 전송 없이 이관대상 건수만 확인)
  const rooms = buildNovaRealtimeMigrationRooms_();
  const sites = Array.from(new Set(rooms.map(row => row.site).filter(Boolean))).sort();
  const users = buildNovaRealtimeMigrationUsers_(sites);
  const roommaidUsers = users.filter(user => user.role === 'ROOMMAID').length;
  const assignedRooms = rooms.filter(room => room.roommaidEmployeeNo || room.secondaryRoommaidEmployeeNo).length;
  const result = {
    ok: true,
    users: users.length,
    roommaidUsers: roommaidUsers,
    rooms: rooms.length,
    assignedRooms: assignedRooms,
    sites: sites
  };
  console.log(JSON.stringify(result, null, 2));
  return result;
}

function buildNovaRealtimeMigrationUsers_(sites) { // (사용자계정 PostgreSQL 이관형식 변환)
  const sheet = novaRealtimeMigrationGetSheet_('사용자계정');
  if (sheet.getLastRow() < 2) return [];
  const values = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getDisplayValues();
  const headers = values[0].map(value => String(value || '').trim());
  const map = novaRealtimeMigrationHeaderMap_(headers);
  const allowedRoles = ['ADMIN', 'ORDER', 'QM', 'HOUSEMAN', 'ROOMMAID', 'PUBLIC'];
  const result = [];
  const seen = {};

  values.slice(1).forEach((row, index) => {
    const employeeNo = novaRealtimeMigrationCell_(row, map, '사번');
    const name = novaRealtimeMigrationCell_(row, map, '이름');
    const role = novaRealtimeMigrationCell_(row, map, '권한').toUpperCase();
    if (!employeeNo || !name || !allowedRoles.includes(role)) return;
    if (seen[employeeNo]) throw new Error('사용자계정 사번이 중복되었습니다: ' + employeeNo + ' (' + (index + 2) + '행)');
    seen[employeeNo] = true;
    const enabledText = novaRealtimeMigrationCell_(row, map, '사용여부').toUpperCase();
    const enabled = !['N', '미사용', '사용안함', 'FALSE', '0'].includes(enabledText);
    const defaultSite = novaRealtimeMigrationCell_(row, map, '기본사업장');
    let allowedSites = [];
    if (role === 'ADMIN' || role === 'ORDER') {
      allowedSites = (sites || []).slice();
    } else if (defaultSite) {
      allowedSites = [defaultSite];
    }
    result.push({
      employeeNo: employeeNo,
      name: name,
      role: role,
      enabled: enabled,
      defaultSite: defaultSite,
      allowedSites: allowedSites
    });
  });

  return result;
}

function buildNovaRealtimeMigrationRooms_() { // (현재객실현황 PostgreSQL 이관형식 변환 / 중복 자동정리)
  const sheet = novaRealtimeMigrationGetSheet_('현재객실현황');
  if (sheet.getLastRow() < 2) return [];
  const range = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn());
  const rawValues = range.getValues();
  const displayValues = range.getDisplayValues();
  const headers = displayValues[0].map(value => String(value || '').trim());
  const map = novaRealtimeMigrationHeaderMap_(headers);
  ['업무일자', '사업장', '객실번호', '객실상태', '청소상태'].forEach(header => {
    if (map[header] === undefined) throw new Error('현재객실현황 시트에 ' + header + ' 열이 없습니다.');
  });

  // 현재객실현황에 동일한 업무일자+사업장+객실번호가 여러 번 존재할 수 있습니다.
  // 원본 시트는 수정/삭제하지 않고, 이관할 때만 "시트에서 더 아래쪽 행"을 최신값으로 간주해 1건으로 정리합니다.
  const byKey = {};
  const duplicateKeys = [];
  let duplicateCount = 0;

  for (let i = 1; i < displayValues.length; i++) {
    const displayRow = displayValues[i];
    const rawRow = rawValues[i];
    const businessDate = novaRealtimeMigrationDate_(rawRow[map['업무일자']], displayRow[map['업무일자']]);
    const site = novaRealtimeMigrationCell_(displayRow, map, '사업장');
    const roomNo = novaRealtimeMigrationCell_(displayRow, map, '객실번호');
    if (!businessDate || !site || !roomNo) continue;

    const key = businessDate + '|' + site + '|' + roomNo;
    if (byKey[key]) {
      duplicateCount++;
      if (duplicateKeys.length < 20) {
        duplicateKeys.push(key + ' (' + byKey[key].sourceRow + '행 → ' + (i + 1) + '행)');
      }
    }

    byKey[key] = {
      sourceRow: i + 1,
      room: {
        businessDate: businessDate,
        site: site,
        roomNo: roomNo,
        building: novaRealtimeMigrationCell_(displayRow, map, '동'),
        roomStatus: novaRealtimeMigrationCell_(displayRow, map, '객실상태').toUpperCase(),
        cleaningStatus: (novaRealtimeMigrationCell_(displayRow, map, '청소상태') || 'WAITING').toUpperCase(),
        cleaningType: (novaRealtimeMigrationCell_(displayRow, map, '정비유형') || 'NORMAL').toUpperCase(),
        assignmentType: (novaRealtimeMigrationCell_(displayRow, map, '배정유형') || 'SOLO').toUpperCase(),
        roommaidEmployeeNo: novaRealtimeMigrationCell_(displayRow, map, '룸메이드사번'),
        secondaryRoommaidEmployeeNo: novaRealtimeMigrationCell_(displayRow, map, '보조룸메이드사번'),
        qmEmployeeNo: novaRealtimeMigrationCell_(displayRow, map, 'QM사번'),
        operationalStatus: novaRealtimeMigrationCell_(displayRow, map, '객실운영상태')
      }
    };
  }

  const entries = Object.keys(byKey)
    .map(key => byKey[key])
    .sort((a, b) => a.sourceRow - b.sourceRow);

  if (duplicateCount > 0) {
    console.log(
      '[NOVA Realtime Migration] 현재객실현황 중복 ' + duplicateCount +
      '건 자동정리. 같은 업무일자+사업장+객실번호는 더 아래쪽 행을 사용합니다.'
    );
    duplicateKeys.forEach(item => console.log('  - ' + item));
    if (duplicateCount > duplicateKeys.length) {
      console.log('  - 그 외 ' + (duplicateCount - duplicateKeys.length) + '건');
    }
  }

  return entries.map(entry => entry.room);
}

function novaRealtimeMigrationGetSheet_(name) { // (기존 NOVA 시트 접근 우선 사용)
  if (typeof getRequiredSheet_ === 'function') return getRequiredSheet_(name);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('연결된 스프레드시트를 찾지 못했습니다.');
  const sheet = ss.getSheetByName(name);
  if (!sheet) throw new Error(name + ' 시트를 찾지 못했습니다.');
  return sheet;
}

function novaRealtimeMigrationHeaderMap_(headers) { // (헤더명 -> 0기준 열번호)
  const map = {};
  (headers || []).forEach((header, index) => {
    const key = String(header || '').trim();
    if (key && map[key] === undefined) map[key] = index;
  });
  return map;
}

function novaRealtimeMigrationCell_(row, map, header) { // (표시값 안전 읽기)
  const index = map[header];
  if (index === undefined) return '';
  return String(row[index] == null ? '' : row[index]).trim();
}

function novaRealtimeMigrationDate_(raw, display) { // (업무일자 yyyy-MM-dd 정규화)
  if (Object.prototype.toString.call(raw) === '[object Date]' && !isNaN(raw.getTime())) {
    return Utilities.formatDate(raw, 'Asia/Seoul', 'yyyy-MM-dd');
  }
  const text = String(display || raw || '').trim();
  if (!text) return '';
  const match = text.match(/^(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!match) return '';
  return match[1] + '-' + String(match[2]).padStart(2, '0') + '-' + String(match[3]).padStart(2, '0');
}

function novaRealtimeMigrationHmacHex_(message, secret) { // (Cloud Run 최초이관 HMAC 서명)
  const bytes = Utilities.computeHmacSha256Signature(
    String(message || ''),
    String(secret || ''),
    Utilities.Charset.UTF_8
  );
  return bytes.map(byte => {
    const value = byte < 0 ? byte + 256 : byte;
    return ('0' + value.toString(16)).slice(-2);
  }).join('');
}
