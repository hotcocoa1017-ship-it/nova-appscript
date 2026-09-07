from pathlib import Path
import sys

PATH = Path('DailyCloseDbFirstBridge.js')
MARKER = 'DAILY_CLOSE_SAVE_FALLBACK_FAILSAFE_V1'


def fail(message):
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(97)


text = PATH.read_text(encoding='utf-8')
if MARKER in text:
    print(f'{MARKER} already applied.')
    raise SystemExit(0)

old1 = """    const results = [];
    prepared.forEach(item => {
      const requestId = String(safe.requestId || novaDbFirstRequestId_(`DAILY_CLOSE_${item.site}`)).trim();
"""
new1 = """    const results = [];
    let saveLegacyFallback = false; // DAILY_CLOSE_SAVE_FALLBACK_FAILSAFE_V1
    prepared.forEach(item => {
      if (saveLegacyFallback) return;
      const requestId = String(safe.requestId || novaDbFirstRequestId_(`DAILY_CLOSE_${item.site}`)).trim();
"""
if text.count(old1) != 1:
    fail(f'daily close results anchor expected once, found {text.count(old1)}')
text = text.replace(old1, new1, 1)

old2 = """      if (db && db.legacyFallback) {
        if (results.length) throw new Error('일부 사업장 DB 마감이 이미 확정되어 legacy 저장으로 전환할 수 없습니다.');
        return;
      }
"""
new2 = """      if (db && db.legacyFallback) {
        if (results.length) throw new Error('일부 사업장 DB 마감이 이미 확정되어 legacy 저장으로 전환할 수 없습니다.');
        saveLegacyFallback = true;
        return;
      }
"""
if text.count(old2) != 1:
    fail(f'daily close save fallback anchor expected once, found {text.count(old2)}')
text = text.replace(old2, new2, 1)

old3 = """    if (!results.length && mustLegacyFallback) return saveDailyCloseSnapshot(token, payload);
    return {
"""
new3 = """    if (saveLegacyFallback) return saveDailyCloseSnapshot(token, payload);
    if (!results.length && mustLegacyFallback) return saveDailyCloseSnapshot(token, payload);
    return {
"""
if text.count(old3) != 1:
    fail(f'daily close final fallback anchor expected once, found {text.count(old3)}')
text = text.replace(old3, new3, 1)

PATH.write_text(text, encoding='utf-8')
print(f'{MARKER} applied.')
