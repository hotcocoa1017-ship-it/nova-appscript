-- NOVA PWA V2 public static asset bucket.
insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types)
values (
  'nova-pwa-v2','nova-pwa-v2',true,2097152,
  array['text/html','application/manifest+json','application/javascript','image/png']::text[]
)
on conflict (id) do update
set public=true,
    file_size_limit=excluded.file_size_limit,
    allowed_mime_types=excluded.allowed_mime_types;
