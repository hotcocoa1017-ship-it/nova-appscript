from pathlib import Path
import sys

client_path = Path('ArchiveAdminClient.html')
rt_path = Path('ArchiveAdminRealtimeClient.html')
client = client_path.read_text(encoding='utf-8')
rt = rt_path.read_text(encoding='utf-8')
marker = 'ARCHIVE_PRUNE_REALTIME_REFRESH_V1'

if marker in client and marker in rt:
    print('Archive prune realtime refresh patch already applied.')
    sys.exit(0)

if 'ARCHIVE_PRUNE_ADMIN_STATUS_V1' not in client:
    print('ERROR: Archive prune admin UI patch must run first.', file=sys.stderr)
    sys.exit(90)

if marker not in client:
    anchor = "  function renderArchiveStatusError_(message) {\n"
    insert = "  window.novaArchiveRenderPruneStatus_ = renderArchivePrune_; // ARCHIVE_PRUNE_REALTIME_REFRESH_V1\n\n" + anchor
    if client.count(anchor) != 1:
        print(f'ERROR: prune renderer exposure anchor count={client.count(anchor)}', file=sys.stderr)
        sys.exit(91)
    client = client.replace(anchor, insert, 1)

if marker not in rt:
    status_anchor = """      if (result?.ok && result?.current && archiveRtPageVisible_()) {
        archiveRtRenderIntegrity_(result.current, sourceLabel || '서버 확인');
      }
"""
    status_insert = """      if (result?.ok && result?.current && archiveRtPageVisible_()) {
        archiveRtRenderIntegrity_(result.current, sourceLabel || '서버 확인');
        if (result?.prune && typeof window.novaArchiveRenderPruneStatus_ === 'function') {
          window.novaArchiveRenderPruneStatus_(result.prune); // ARCHIVE_PRUNE_REALTIME_REFRESH_V1
        }
      }
"""
    if rt.count(status_anchor) != 1:
        print(f'ERROR: realtime status refresh anchor count={rt.count(status_anchor)}', file=sys.stderr)
        sys.exit(92)
    rt = rt.replace(status_anchor, status_insert, 1)

    message_anchor = """    archiveRtRenderIntegrity_(integrity, '실시간 반영');
    archiveRtScheduleQueryRefresh_();
"""
    message_insert = """    archiveRtRenderIntegrity_(integrity, '실시간 반영');
    void archiveRtRefreshStatus_('실시간 반영');
    archiveRtScheduleQueryRefresh_();
"""
    if rt.count(message_anchor) != 1:
        print(f'ERROR: realtime message refresh anchor count={rt.count(message_anchor)}', file=sys.stderr)
        sys.exit(93)
    rt = rt.replace(message_anchor, message_insert, 1)

client_path.write_text(client, encoding='utf-8')
rt_path.write_text(rt, encoding='utf-8')
print('Applied Archive prune realtime refresh patch.')
