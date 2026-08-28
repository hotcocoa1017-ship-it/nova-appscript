from pathlib import Path

PATH = Path('cloudrun/index.js')
text = PATH.read_text(encoding='utf-8')
original = text


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ERROR: {label}: expected 1 match, found {count}')
    text = text.replace(old, new, 1)

replace_once(
"""      const requester =
        cleanText_(
          body.requester
          || '오더테이커',
          120
        );
""",
"""      let requester =
        cleanText_(
          body.requester
          || '오더테이커',
          120
        );
""",
'houseman requester mutable for mobile source'
)

replace_once(
"""      if (
        ![
          'ADMIN',
          'ORDER'
        ].includes(
          user.role
        )
      ) {

        throw httpError(
          403,
          'FORBIDDEN',
          '하우스맨 오더 등록 권한이 없습니다.'
        );
      }

      if (
        !allowedForSite(
          user,
          site
        )
      ) {

        throw httpError(
          403,
          'FORBIDDEN',
          '해당 사업장 처리 권한이 없습니다.'
        );
      }
""",
"""      const requestRole =
        String(user.role || '')
          .trim()
          .toUpperCase();

      if (
        ![
          'ADMIN',
          'ORDER',
          'ROOMMAID'
        ].includes(
          requestRole
        )
      ) {

        throw httpError(
          403,
          'FORBIDDEN',
          '하우스맨 오더 등록 권한이 없습니다.'
        );
      }

      if (
        !allowedForSite(
          user,
          site
        )
      ) {

        throw httpError(
          403,
          'FORBIDDEN',
          '해당 사업장 처리 권한이 없습니다.'
        );
      }

      // 룸메이드 모바일 오더는 기존과 동일하게 본인 배정객실에서만 허용한다.
      // DB에서 권한을 검증하고 오더 자체는 미배정으로 즉시 확정한다.
      if (requestRole === 'ROOMMAID') {
        if (assignmentMode !== 'UNASSIGNED') {
          throw httpError(
            400,
            'ROOMMAID_ORDER_MUST_BE_UNASSIGNED',
            '룸메이드 요청은 미배정 오더로 등록해야 합니다.'
          );
        }

        const roomAccess = await client.query(
          `select roommaid_employee_no, secondary_roommaid_employee_no
             from public.nova_rooms_current
            where business_date=$1::date
              and site=$2
              and room_no=$3
            limit 1`,
          [businessDate, site, roomNo]
        );
        const currentRoom = roomAccess.rows[0] || null;
        if (!currentRoom) {
          throw httpError(404, 'ROOM_NOT_FOUND', '객실을 찾을 수 없습니다.');
        }
        const assignedRoommaids = [
          String(currentRoom.roommaid_employee_no || ''),
          String(currentRoom.secondary_roommaid_employee_no || '')
        ].filter(Boolean);
        if (!assignedRoommaids.includes(String(user.employee_no || ''))) {
          throw httpError(
            403,
            'FORBIDDEN',
            '본인에게 배정된 객실에서만 요청할 수 있습니다.'
          );
        }
        requester = String(user.name || requester || user.employee_no || '').trim();
      }
""",
'houseman create role and roommaid room authorization'
)

if text == original:
    raise SystemExit('PATCH_ERROR: no changes made')

# Scope/safety guards.
required = [
    "'ROOMMAID'",
    "ROOMMAID_ORDER_MUST_BE_UNASSIGNED",
    "본인에게 배정된 객실에서만 요청할 수 있습니다.",
    "from public.nova_rooms_current",
    "'/v1/houseman-orders'",
]
for token in required:
    if token not in text:
        raise SystemExit(f'PATCH_ERROR: required token missing: {token}')

# Existing manager and DB dedup flow must remain.
for token in ["'ADMIN'", "'ORDER'", "nova_request_dedup", "HOUSEMAN_CREATE", "insert into public.nova_houseman_orders"]:
    if token not in text:
        raise SystemExit(f'PATCH_ERROR: protected houseman path missing: {token}')

PATH.write_text(text, encoding='utf-8')
print('ROOMMAID_HOUSEMAN_CLOUDRUN_V65_OK')
print('Changed: cloudrun/index.js only')
print('ROOMMAID: assigned-room authorization in PostgreSQL, UNASSIGNED realtime create')
print('ADMIN/ORDER: existing create flow preserved')
print('Request dedup: preserved')
