from pathlib import Path

MARKER = "HOUSEMAN_LOST_FOUND_SHORTCUT_V1"
TARGET = Path("Client.html")

text = TARGET.read_text(encoding="utf-8")
if MARKER in text:
    print(f"{MARKER} already applied.")
    raise SystemExit(0)

guard_old = "    if (!['ADMIN', 'ORDER'].includes(role)) return items;"
guard_new = "    if (!['ADMIN', 'ORDER', 'HOUSEMAN'].includes(role)) return items; // HOUSEMAN_LOST_FOUND_SHORTCUT_V1"
if text.count(guard_old) != 1:
    raise SystemExit(f"Expected exactly one role guard, found {text.count(guard_old)}")
text = text.replace(guard_old, guard_new, 1)

sales_anchor = "    if (!items.some(item => item && item.id === 'salesShortcut')) {"
if text.count(sales_anchor) != 1:
    raise SystemExit(f"Expected exactly one sales shortcut anchor, found {text.count(sales_anchor)}")
text = text.replace(
    sales_anchor,
    "    if (role === 'HOUSEMAN') return items; // HOUSEMAN은 습득물 관리 바로가지만 추가\n" + sales_anchor,
    1,
)

TARGET.write_text(text, encoding="utf-8")
print(f"Applied {MARKER}")
