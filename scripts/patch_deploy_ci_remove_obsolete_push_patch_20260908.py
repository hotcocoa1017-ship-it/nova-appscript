from pathlib import Path

path = Path('.github/workflows/deploy-apps-script.yml')
text = path.read_text(encoding='utf-8')

step = """      - name: Apply Realtime subscription resilience patch\n        run: python3 scripts/patch_realtime_subscription_resilience.py\n\n"""
if step in text:
    text = text.replace(step, '', 1)

idempotence = "          python3 scripts/patch_realtime_subscription_resilience.py\n"
if idempotence in text:
    text = text.replace(idempotence, '', 1)

# 기능 자체의 회귀검증은 유지해야 합니다.
if 'grep -q "REALTIME_SUBSCRIPTION_RESILIENCE_V1" Client.html' not in text:
    raise SystemExit('Realtime subscription resilience regression marker missing')

if 'scripts/patch_realtime_subscription_resilience.py' in text:
    raise SystemExit('Obsolete realtime/PWA patch execution still present in deploy workflow')

path.write_text(text, encoding='utf-8')
print('Removed obsolete realtime subscription/PWA patch execution from deployment CI.')
