from pathlib import Path
import sys

CLIENT = Path('Client.html')
MARKER = 'SHIFT_ZONE_DB_FIRST_CLIENT_V3'


def fail(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    raise SystemExit(93)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        if count == 0 and new in text:
            return text
        fail(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)


text = CLIENT.read_text(encoding='utf-8')
if MARKER in text:
    print('SHIFT_ZONE_DB_FIRST_CLIENT_V3 already applied.')
    raise SystemExit(0)

text = replace_once(
    text,
    "      const result = await callServer('getShiftManagementData', state.token, {\n",
    "      const result = await callServer('getShiftManagementDataDbFirst', state.token, { // SHIFT_ZONE_DB_FIRST_CLIENT_V3\n",
    'shift management DB read route'
)
text = replace_once(
    text,
    "      const result = await callServer('saveShiftAssignments', state.token, {\n        businessDate: state.shifts.businessDate,\n        site: state.shifts.site,\n        assignments\n      });",
    "      const result = await callServer('saveShiftAssignmentsDbFirst', state.token, { // SHIFT_ZONE_DB_FIRST_CLIENT_V3\n        businessDate: state.shifts.businessDate,\n        site: state.shifts.site,\n        assignments,\n        requestId: novaRealtimeRequestId_('SHIFT_SAVE_V3', state.shifts.site || '')\n      });",
    'shift save DB-first route'
)
text = replace_once(
    text,
    "      const result = await callServer('saveHousemanZoneAssignment', state.token, {\n        businessDate: state.shifts.businessDate,\n        site: state.shifts.site,\n        employeeNo,\n        buildings: state.shifts.zoneDraft.buildings,\n        action\n      });",
    "      const result = await callServer('saveHousemanZoneAssignmentDbFirst', state.token, { // SHIFT_ZONE_DB_FIRST_CLIENT_V3\n        businessDate: state.shifts.businessDate,\n        site: state.shifts.site,\n        employeeNo,\n        buildings: state.shifts.zoneDraft.buildings,\n        action,\n        requestId: novaRealtimeRequestId_(`ZONE_${action}_V3`, employeeNo)\n      });",
    'zone save DB-first route'
)

CLIENT.write_text(text, encoding='utf-8')
print('SHIFT_ZONE_DB_FIRST_CLIENT_V3 applied.')
