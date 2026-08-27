from pathlib import Path

path = Path('Styles.html')
text = path.read_text(encoding='utf-8')

old = "grid-template-columns: 148px 150px minmax(190px, 1fr) auto auto;"
new = "grid-template-columns: 190px 150px minmax(190px, 1fr) auto auto;"

if new in text:
    print('Indicator business-date width already applied')
elif text.count(old) == 1:
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')
    print('Widened indicator business-date column from 148px to 190px')
else:
    raise SystemExit(f'Expected exactly one indicator controls desktop grid marker, found {text.count(old)}')

# Guardrails: change only the first desktop control column; keep site/search/action columns intact.
result = path.read_text(encoding='utf-8')
if new not in result:
    raise SystemExit('Indicator date width change was not applied')
if "grid-template-columns: 190px 150px minmax(190px, 1fr) auto auto;" not in result:
    raise SystemExit('Neighboring indicator control widths changed unexpectedly')
