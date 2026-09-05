-- NOVA Realtime + Archive performance follow-up
-- Applied to Supabase nova-realtime on 2026-09-05.
-- 1) Avoid per-row current_setting() evaluation in the Realtime receive policy.
-- 2) Add the missing covering index for archive_jobs.batch_id.

DROP POLICY IF EXISTS "nova realtime receive by site" ON realtime.messages;
CREATE POLICY "nova realtime receive by site"
ON realtime.messages
FOR SELECT
TO authenticated
USING (
  extension = 'broadcast'
  AND (
    EXISTS (
      SELECT 1
      FROM jsonb_array_elements_text(
        COALESCE(
          (((SELECT current_setting('request.jwt.claims', true)))::jsonb -> 'sites'),
          '[]'::jsonb
        )
      ) AS s(site_name)
      WHERE realtime.topic() = ('nova:site:' || s.site_name || ':rooms')
    )
    OR public.nova_realtime_topic_allowed(realtime.topic())
  )
);

COMMENT ON POLICY "nova realtime receive by site" ON realtime.messages IS
'NOVA site-scoped room broadcast receive policy. request.jwt.claims is wrapped as an initPlan subquery to avoid per-row current_setting evaluation under high Realtime fan-out.';

CREATE INDEX IF NOT EXISTS nova_archive_jobs_batch_id_idx
ON public.nova_archive_jobs(batch_id)
WHERE batch_id IS NOT NULL;
