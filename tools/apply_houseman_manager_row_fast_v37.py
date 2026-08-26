from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"SKIP {label}: already applied")
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"PATCH FAIL {label}: expected 1 match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PATCH OK {label}")


client = Path("Client.html")

# 관리자/오더테이커의 단건 오더 변경은 이미 화면 객체에 HISTORY 행번호를 가지고 있습니다.
# 기존에는 ASSIGN/상태변경 요청에 rowNumber를 보내지 않아 서버가 매번 업무이력 전체 기록ID 열을
# TextFinder로 검색했습니다. 대형 HISTORY 시트에서 이 검색이 7~10초 지연의 주 원인이 될 수 있으므로
# 기존 findHousemanOrderRow_의 '행번호 우선 조회 -> 불일치 시 ID 검색' 경로를 그대로 활용합니다.
old_action_payload = """    const payload = { orderId: order.orderId, action, expectedVersion: Number(order.version || 0) };
"""
new_action_payload = """    const payload = {
      orderId: order.orderId,
      action,
      expectedVersion: Number(order.version || 0),
      rowNumber: Number(order.rowNumber || 0)
    };
"""
replace_once(client, old_action_payload, new_action_payload, "Manager houseman action preferred row")

# 수정(EDIT)도 동일한 단건 행을 대상으로 하므로 같은 최적화를 적용합니다.
old_edit_payload = """        const result = await callServer('updateHousemanOrder', state.token, {
          orderId: order.orderId,
          action: 'EDIT',
          expectedVersion: Number(order.version || 0),
          part: $('editOrderPart').value,
"""
new_edit_payload = """        const result = await callServer('updateHousemanOrder', state.token, {
          orderId: order.orderId,
          action: 'EDIT',
          expectedVersion: Number(order.version || 0),
          rowNumber: Number(order.rowNumber || 0),
          part: $('editOrderPart').value,
"""
replace_once(client, old_edit_payload, new_edit_payload, "Manager houseman edit preferred row")

text = client.read_text(encoding="utf-8")
required = [
    "rowNumber: Number(order.rowNumber || 0)",
    "action: 'EDIT',\n          expectedVersion: Number(order.version || 0),\n          rowNumber: Number(order.rowNumber || 0),",
    "if (!safePayload.rowNumber) safePayload.rowNumber = Number(order?.rowNumber || 0);"
]
for marker in required:
    if marker not in text:
        raise SystemExit(f"VERIFY FAIL Client marker missing: {marker}")

print("VERIFY PASS manager houseman preferred-row fast path; mobile preferred-row preserved")
