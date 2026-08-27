from pathlib import Path

path = Path('Styles.html')
text = path.read_text(encoding='utf-8')

old = "grid-template-columns: 148px 220px minmax(180px, 1fr) auto;"
new = "grid-template-columns: 190px 220px minmax(180px, 1fr) auto;"

if new in text:
    print('Indicator business-date width already applied')
elif text.count(old) == 1:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
    print('Widened indicator business-date column from 148px to 190px')
else:
    raise SystemExit(f'Expected exactly one indicator controls desktop grid marker, found {text.count(old)}')

# Guardrails: keep the existing responsive layout and neighboring control widths unchanged.
result = path.read_text(encoding='utf-8')
if new not in result:
    raise SystemExit('Indicator date width change was not applied')
if '@media (max-width: 1180px)' not in result or '.indicator-controls { grid-template-columns: 1fr 1fr; }' not in result:
    raise SystemExit('Existing responsive indicator controls layout marker was lost')
