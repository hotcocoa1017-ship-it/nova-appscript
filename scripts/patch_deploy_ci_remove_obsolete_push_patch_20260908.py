from pathlib import Path

workflow_path = Path('.github/workflows/deploy-apps-script.yml')
workflow = workflow_path.read_text(encoding='utf-8')

step = """      - name: Apply Realtime subscription resilience patch\n        run: python3 scripts/patch_realtime_subscription_resilience.py\n\n"""
if step in workflow:
    workflow = workflow.replace(step, '', 1)

idempotence = "          python3 scripts/patch_realtime_subscription_resilience.py\n"
if idempotence in workflow:
    workflow = workflow.replace(idempotence, '', 1)

# 기능 자체의 회귀검증은 유지해야 합니다.
marker_check = 'grep -q "REALTIME_SUBSCRIPTION_RESILIENCE_V1" Client.html'
if marker_check not in workflow:
    raise SystemExit('Realtime subscription resilience regression marker missing')
if 'scripts/patch_realtime_subscription_resilience.py' in workflow:
    raise SystemExit('Obsolete realtime/PWA patch execution still present in deploy workflow')
workflow_path.write_text(workflow, encoding='utf-8')

release_path = Path('scripts/validate_nova_release.py')
release = release_path.read_text(encoding='utf-8')
old = "require(workflow, 'python3 scripts/patch_realtime_subscription_resilience.py', 'Deploy applies Realtime subscription resilience patch')"
new = "forbid(workflow, 'python3 scripts/patch_realtime_subscription_resilience.py', 'Obsolete Realtime/PWA patch execution removed from deploy')\nrequire(workflow, 'grep -q \\\"REALTIME_SUBSCRIPTION_RESILIENCE_V1\\\" Client.html', 'Deploy validates Realtime subscription resilience marker')"
if old in release:
    release = release.replace(old, new, 1)
elif new not in release:
    raise SystemExit('Release validator Realtime/PWA CI anchor missing')
release_path.write_text(release, encoding='utf-8')

print('Removed obsolete realtime subscription/PWA patch execution and updated release gate.')
