from pathlib import Path

MARKER = 'QM_DRAFT_CANARY_Q001_V1'
path = Path('RealtimeBridge.js')
text = path.read_text(encoding='utf-8')

if MARKER in text:
    print('q001 canary already applied.')
    raise SystemExit(0)

old = """  let qmDraftDbFirstEnabled = false;
  const qmDraftMasterEnabled = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED') || 'N').trim().toUpperCase() === 'Y';
  const qmDraftEmployees = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES') || '')
    .split(',').map(value => value.trim()).filter(Boolean);
  if (qmDraftMasterEnabled && qmDraftEmployees.length && token) {
    const verified = verifyNovaToken(token);
    const user = verified && verified.ok ? verified.user : null;
    qmDraftDbFirstEnabled = Boolean(user
      && String(user.role || '').trim().toUpperCase() === 'QM'
      && qmDraftEmployees.includes(String(user.employeeNo || '').trim()));
  }
"""
new = """  let qmDraftDbFirstEnabled = false;
  const qmDraftMode = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED') || 'CANARY').trim().toUpperCase();
  const qmDraftConfiguredEmployees = String(props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES') || '')
    .split(',').map(value => value.trim()).filter(Boolean);
  const qmDraftCanaryEmployees = Object.freeze(['q001']); // QM_DRAFT_CANARY_Q001_V1
  const qmDraftEmployees = qmDraftMode === 'CANARY' ? Array.from(qmDraftCanaryEmployees) : qmDraftConfiguredEmployees;
  const qmDraftMasterEnabled = qmDraftMode === 'CANARY' || qmDraftMode === 'Y';
  if (qmDraftMasterEnabled && qmDraftEmployees.length && token) {
    const verified = verifyNovaToken(token);
    const user = verified && verified.ok ? verified.user : null;
    qmDraftDbFirstEnabled = Boolean(user
      && String(user.role || '').trim().toUpperCase() === 'QM'
      && qmDraftEmployees.includes(String(user.employeeNo || '').trim()));
  }
"""
if old not in text:
    raise SystemExit('QM draft canary config anchor not found')
text = text.replace(old, new, 1)

old_setup = """  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED', 'N');
  }
  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', '');
  }
"""
new_setup = """  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_ENABLED', 'CANARY');
  }
  if (!props.getProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES')) {
    props.setProperty('NOVA_QM_DRAFT_DB_FIRST_EMPLOYEES', 'q001');
  }
"""
if old_setup not in text:
    raise SystemExit('QM draft canary setup anchor not found')
text = text.replace(old_setup, new_setup, 1)

path.write_text(text, encoding='utf-8')
print('Applied QM_DRAFT_CANARY_Q001_V1.')
