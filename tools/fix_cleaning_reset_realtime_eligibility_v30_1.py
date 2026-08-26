#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "cloudrun" / "index.js"

old = """        const previousCleaningStatus = String(room.cleaning_status || '').trim().toUpperCase();
        const resetAllowedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
        if (!resetAllowedStatuses.has(previousCleaningStatus)) {
          throw httpError(400, 'INVALID_STATE', '청소완료 상태에서만 청소초기화할 수 있습니다.');
        }
"""

new = """        const roomStatus = String(room.room_status || '').trim().toUpperCase();
        const resetAllowedRoomStatuses = new Set([
          'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU',
          'STOCK', 'STOCK_RC', 'STOCK_HU'
        ]);
        if (!resetAllowedRoomStatuses.has(roomStatus)) {
          throw httpError(400, 'INVALID_STATE', `${roomNo}호는 청소초기화 대상 객실상태가 아닙니다.`);
        }

        const previousCleaningStatus = String(room.cleaning_status || '').trim().toUpperCase();
        const resetAllowedStatuses = new Set(['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']);
        if (!resetAllowedStatuses.has(previousCleaningStatus)) {
          throw httpError(400, 'INVALID_STATE', '청소완료 상태에서만 청소초기화할 수 있습니다.');
        }
"""

text = TARGET.read_text(encoding="utf-8")
if text.count(old) != 1:
    print(f"PATCH_ERROR: expected CLEANING_RESET eligibility anchor once, found {text.count(old)}")
    sys.exit(1)

text = text.replace(old, new, 1)
TARGET.write_text(text, encoding="utf-8")

check = subprocess.run(["node", "--check", str(TARGET)], capture_output=True, text=True)
if check.returncode != 0:
    print(check.stdout)
    print(check.stderr)
    sys.exit(check.returncode)

required = [
    "'CHECKED_OUT', 'CHECKED_OUT_RC', 'CHECKED_OUT_HU'",
    "'STOCK', 'STOCK_RC', 'STOCK_HU'",
    "청소초기화 대상 객실상태가 아닙니다.",
    "['COMPLETED', 'QM_WAITING', 'QM_CHECKING', 'QM_COMPLETED']",
]
for marker in required:
    if marker not in text:
        print(f"VERIFY_ERROR: missing marker: {marker}")
        sys.exit(1)

print("PATCH_OK")
print("Repository only; production Cloud Run / Apps Script NOT changed yet")
print("Changed: cloudrun/index.js only")
print("Fixed: Realtime CLEANING_RESET now preserves legacy room-status eligibility")
print("Allowed room statuses: CHECKED_OUT / CHECKED_OUT_RC / CHECKED_OUT_HU / STOCK / STOCK_RC / STOCK_HU")
print("Preserved: cleaning-status eligibility, permissions, v30 realtime save/mirror, all other room actions")
print("Cloud Run syntax: PASS")
print("VERIFY: PASS")
