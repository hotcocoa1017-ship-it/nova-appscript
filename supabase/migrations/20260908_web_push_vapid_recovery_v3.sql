-- NOVA Web Push VAPID recovery V3
-- Public VAPID key only. The matching private key remains in Supabase Vault and is never committed.
-- NOVA_PUSH_VAPID_RECOVERY_V3

create or replace function public.nova_web_push_config_service()
returns jsonb
language plpgsql
stable
security definer
set search_path to ''
as $function$
declare
  v_private text;
begin
  select s.decrypted_secret into v_private
  from vault.decrypted_secrets s
  where s.name='nova_web_push_vapid_private_v2'
  limit 1;
  if coalesce(v_private,'')='' then
    raise exception 'VAPID private key unavailable';
  end if;
  return jsonb_build_object(
    'publicKey','BKjiczDO9sG0qlh0rJDduCzQqT9tURU69oKN7mKmlyU4mnjx05x1FkUy-4Kaeqy40DReDmnQ1DR2s0ELu-SAgYM',
    'privateKey',v_private,
    'subject','https://evoetxfjmkkjptucwxsv.supabase.co'
  );
end;
$function$;

revoke all on function public.nova_web_push_config_service() from public, anon, authenticated;
grant execute on function public.nova_web_push_config_service() to service_role;
