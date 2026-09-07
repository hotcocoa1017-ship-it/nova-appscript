from pathlib import Path
import re
from collections import Counter

ROOT = Path('.')
EXCLUDE_DIRS = {'.git', '.github', 'scripts', 'db', 'node_modules'}
EXTENSIONS = {'.js', '.html'}

PATTERNS = [
    ('CURRENT_SHEET', re.compile(r"getRequiredSheet_\(\s*NOVA\.SHEETS\.CURRENT\s*\)")),
    ('HISTORY_SHEET', re.compile(r"getRequiredSheet_\(\s*NOVA\.SHEETS\.HISTORY\s*\)")),
    ('MONTHLY_SHEET_READ', re.compile(r"\breadMonthlyHistoryRows_\s*\(")),
    ('CLOSE_CURRENT_SHEET_READ', re.compile(r"\breadCurrentRowsForClose_\s*\(")),
    ('CLOSE_HISTORY_SHEET_READ', re.compile(r"\breadHistoryRowsForClose_\s*\(")),
    ('CURRENT_SITE_SHEET_READ', re.compile(r"\bgetCurrentSitesForDate_\s*\(")),
    ('FORWARD_SYNC_CALL', re.compile(r"\bsyncNovaRealtimeCurrentBusinessDate\s*\(")),
    ('JIT_SYNC_CALL', re.compile(r"\bsyncNovaRealtimeRoomForAction\s*\(")),
    ('HISTORY_APPEND', re.compile(r"\bappendUnifiedHistory_\s*\(")),
    ('ROW_UPDATE', re.compile(r"\bupdateRowByHeaders_\s*\(")),
]

# These function-name fragments are expected mirror/fallback/recovery infrastructure.
SAFE_FUNCTION_FRAGMENTS = (
    'mirror', 'legacy', 'fallback', 'read', 'build', 'find', 'index', 'syncnovarealtime',
    'prepare', 'test', 'install', 'remove', 'ensure', 'audit', 'history', 'snapshot',
)

# Explicit functions whose Sheet access remains intentionally allowed during DB-first cutover.
SAFE_FUNCTIONS = {
    'novaRealtimeFinalAppendHistoryBatch_',
    'novaRealtimeFinalCurrentRoomIndex_',
    'novaRealtimeFinalFindLatestRoomRow_',
    'novaRealtimeFinalRecentRequestIds_',
    'novaRealtimeFinalBuildRooms_',
    'syncNovaRealtimeQmAssignmentMirror',
    'readMonthlyHistoryRows_',
    'readCurrentRowsForClose_',
    'readHistoryRowsForClose_',
    'getCurrentSitesForDate_',
}


def iter_files():
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        yield path


def function_for_line(lines, target_index):
    current = '<top-level>'
    for i in range(target_index + 1):
        match = re.search(r'\bfunction\s+([A-Za-z0-9_$]+)\s*\(', lines[i])
        if match:
            current = match.group(1)
    return current


def classify(function_name, category, line):
    fn = function_name.lower()
    if function_name in SAFE_FUNCTIONS or any(fragment in fn for fragment in SAFE_FUNCTION_FRAGMENTS):
        return 'ALLOW_MIRROR_FALLBACK'
    # Function declarations are inventory, not callers.
    if re.search(r'^\s*function\s+', line) and category in {
        'MONTHLY_SHEET_READ', 'CLOSE_CURRENT_SHEET_READ', 'CLOSE_HISTORY_SHEET_READ',
        'CURRENT_SITE_SHEET_READ', 'FORWARD_SYNC_CALL', 'JIT_SYNC_CALL'
    }:
        return 'DEFINITION'
    return 'REVIEW_PRIMARY'


def main():
    findings = []
    for path in iter_files():
        text = path.read_text(encoding='utf-8', errors='replace')
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            for category, pattern in PATTERNS:
                if not pattern.search(line):
                    continue
                fn = function_for_line(lines, idx)
                disposition = classify(fn, category, line)
                findings.append({
                    'disposition': disposition,
                    'category': category,
                    'file': str(path),
                    'line': idx + 1,
                    'function': fn,
                    'text': line.strip()[:240],
                })

    counts = Counter(item['disposition'] for item in findings)
    categories = Counter(item['category'] for item in findings)
    out = []
    out.append('NOVA DB CUTOVER RESIDUAL AUDIT V1')
    out.append('================================')
    out.append(f"files_scanned={sum(1 for _ in iter_files())}")
    out.append(f"findings={len(findings)}")
    out.append('disposition=' + ', '.join(f'{k}:{v}' for k, v in sorted(counts.items())))
    out.append('categories=' + ', '.join(f'{k}:{v}' for k, v in sorted(categories.items())))
    out.append('')

    for disposition in ('REVIEW_PRIMARY', 'ALLOW_MIRROR_FALLBACK', 'DEFINITION'):
        group = [item for item in findings if item['disposition'] == disposition]
        out.append(f'[{disposition}] count={len(group)}')
        for item in group:
            out.append(
                f"{item['category']} | {item['file']}:{item['line']} | {item['function']} | {item['text']}"
            )
        out.append('')

    report = '\n'.join(out).rstrip() + '\n'
    Path('db_cutover_residual_audit.txt').write_text(report, encoding='utf-8')
    print(report)

    # Audit mode intentionally does not fail on REVIEW_PRIMARY. The output is used to patch
    # residual paths one by one without accidentally deleting required Sheet mirrors/fallbacks.
    print(f"AUDIT_RESULT review_primary={counts.get('REVIEW_PRIMARY', 0)}")


if __name__ == '__main__':
    main()
