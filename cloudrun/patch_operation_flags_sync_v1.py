from pathlib import Path
import sys

PATH = Path('cloudrun/index.js')
text = PATH.read_text(encoding='utf-8')
MARKER = 'ROOM_OPERATION_FLAGS_SYNC_V1'


def replace_once(old: str, new: str, label: str):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected=1')
    text = text.replace(old, new, 1)


def replace_exact_count(old: str, new: str, expected: int, label: str):
    global text
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'ERROR: {label} anchor count={count}, expected={expected}')
    text = text.replace(old, new)


if MARKER in text:
    print(f'{MARKER} already applied.')
    sys.exit(0)

# 1) All room read responses expose the three DB columns.
replace_once(
    "    operationalStatus: r.operational_status || '',\n    version: Number(r.version || 0),",
    "    operationalStatus: r.operational_status || '',\n"
    "    // ROOM_OPERATION_FLAGS_SYNC_V1 · independent room operation flags\n"
    "    preassigned: r.preassigned === true,\n"
    "    vip: r.vip === true,\n"
    "    importantRoom: r.important_room === true,\n"
    "    version: Number(r.version || 0),",
    'roomDto operation flags'
)

# 2) Signed Sheets -> Cloud Run migration/sync payload retains booleans.
replace_once(
    "    operationalStatus:\n      cleanText_(raw?.operationalStatus, 80)\n  };",
    "    operationalStatus:\n      cleanText_(raw?.operationalStatus, 80),\n"
    "    preassigned: raw?.preassigned === true,\n"
    "    vip: raw?.vip === true,\n"
    "    importantRoom: raw?.importantRoom === true\n"
    "  };",
    'normalizeMigrationRoom operation flags'
)

# 3) Bootstrap and incremental room value tuples expand from 12 -> 15 params.
#    The two blocks use different indentation, so patch them separately.
replace_exact_count(
    "const n = i * 12;",
    "const n = i * 15;",
    2,
    'room tuple parameter width'
)

replace_once(
    "          r.qmEmployeeNo || null,\n          r.operationalStatus\n        );",
    "          r.qmEmployeeNo || null,\n"
    "          r.operationalStatus,\n"
    "          r.preassigned,\n"
    "          r.vip,\n"
    "          r.importantRoom\n"
    "        );",
    'bootstrap room operation flag params'
)
replace_once(
    "              r.qmEmployeeNo || null,\n              r.operationalStatus\n            );",
    "              r.qmEmployeeNo || null,\n"
    "              r.operationalStatus,\n"
    "              r.preassigned,\n"
    "              r.vip,\n"
    "              r.importantRoom\n"
    "            );",
    'sync room operation flag params'
)

replace_once(
    "          $${n + 11},\n          $${n + 12}\n        )`;",
    "          $${n + 11},\n"
    "          $${n + 12},\n"
    "          $${n + 13}::boolean,\n"
    "          $${n + 14}::boolean,\n"
    "          $${n + 15}::boolean\n"
    "        )`;",
    'bootstrap operation flag placeholders'
)
replace_once(
    "              $${n + 11},\n              $${n + 12}\n            )`;",
    "              $${n + 11},\n"
    "              $${n + 12},\n"
    "              $${n + 13}::boolean,\n"
    "              $${n + 14}::boolean,\n"
    "              $${n + 15}::boolean\n"
    "            )`;",
    'sync operation flag placeholders'
)

replace_once(
    "          qm_employee_no,\n          operational_status\n        )",
    "          qm_employee_no,\n"
    "          operational_status,\n"
    "          preassigned,\n"
    "          vip,\n"
    "          important_room\n"
    "        )",
    'bootstrap operation flag columns'
)
replace_once(
    "            qm_employee_no,\n            operational_status\n          )",
    "            qm_employee_no,\n"
    "            operational_status,\n"
    "            preassigned,\n"
    "            vip,\n"
    "            important_room\n"
    "          )",
    'sync operation flag columns'
)

# 4) Incremental sync updates flags from the signed Sheet payload without touching
#    unrelated cleaning/version ownership rules.
replace_once(
    "            operational_status=\n              excluded.operational_status,\n\n            version=",
    "            operational_status=\n              excluded.operational_status,\n\n"
    "            preassigned=excluded.preassigned,\n"
    "            vip=excluded.vip,\n"
    "            important_room=excluded.important_room,\n\n"
    "            version=",
    'sync-current-rooms conflict update operation flags'
)

# 5) Generic Cloud Run UPDATE_OPERATION_FLAGS must mutate the DB columns, not only
#    increment version and emit an event.
replace_once(
    "        const updated = await client.query(\n          `update public.nova_rooms_current\n              set version=version+1,\n                  updated_by=$4,\n                  updated_at=now()\n            where business_date=$1 and site=$2 and room_no=$3\n            returning *`,\n          [businessDate, site, roomNo, user.employee_no]\n        );",
    "        const updated = await client.query(\n"
    "          `update public.nova_rooms_current\n"
    "              set preassigned=$4,\n"
    "                  vip=$5,\n"
    "                  important_room=$6,\n"
    "                  version=version+1,\n"
    "                  updated_by=$7,\n"
    "                  updated_at=now()\n"
    "            where business_date=$1 and site=$2 and room_no=$3\n"
    "            returning *`,\n"
    "          [businessDate, site, roomNo, preassigned, vip, importantRoom, user.employee_no]\n"
    "        );",
    'UPDATE_OPERATION_FLAGS DB mutation'
)

PATH.write_text(text, encoding='utf-8')
print(f'Applied {MARKER}: Cloud Run room flags normalized, synced, persisted, and returned.')
