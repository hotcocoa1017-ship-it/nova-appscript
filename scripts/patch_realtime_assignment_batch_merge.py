from pathlib import Path
import sys

path = Path('RealtimeDailySync.js')
text = path.read_text(encoding='utf-8')
marker = 'REALTIME_ASSIGNMENT_BATCH_MERGE_V1'

if marker in text:
    print('Realtime assignment batch merge patch already applied.')
    sys.exit(0)

old = "  const latestByRow = new Map();\n  updates.forEach(item => latestByRow.set(Number(item.rowNumber), item));\n"
new = """  const latestByRow = new Map(); // REALTIME_ASSIGNMENT_BATCH_MERGE_V1
  updates.forEach(item => {
    const rowNumber = Number(item.rowNumber);
    const previous = latestByRow.get(rowNumber) || {};
    // 같은 1분 배치의 ASSIGN -> START -> COMPLETE가 이어져도 앞 이벤트의 배정 필드를 보존합니다.
    // 뒤 이벤트는 자신이 명시한 필드만 덮어쓰며, RESET/CLEAR처럼 빈 값을 명시한 경우에는 정상적으로 초기화됩니다.
    latestByRow.set(rowNumber, Object.assign({}, previous, item, { rowNumber }));
  });
"""

count = text.count(old)
if count != 1:
    print(f'ERROR: Expected exactly one batch merge anchor, found {count}.', file=sys.stderr)
    sys.exit(70)

text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('Applied Realtime roommaid assignment batch merge patch.')
