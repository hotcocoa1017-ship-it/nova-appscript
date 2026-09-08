-- NOVA Web Push VAPID recovery V4
-- Public/private key pair is provisioned atomically in Vault; secret values are never stored in Git.
-- Required Vault secrets: nova_web_push_vapid_public_v2, nova_web_push_vapid_private_v2

create or replace function public.nova_web_push_config_service()
returns jsonb
language plpgsql
stable
security definer
set search_path to ''
as $function$
declare
  v_public text;
  v_private text;
begin
  select s.decrypted_secret into v_public
  from vault.decrypted_secrets s
  where s.name='nova_web_push_vapid_public_v2'
  limit 1;
  select s.decrypted_secret into v_private
  from vault.decrypted_secrets s
  where s.name='nova_web_push_vapid_private_v2'
  limit 1;
  if coalesce(v_public,'')='' then raise exception 'VAPID public key unavailable'; end if;
  if coalesce(v_private,'')='' then raise exception 'VAPID private key unavailable'; end if;
  return jsonb_build_object(
    'publicKey',v_public,
    'privateKey',v_private,
    'subject','https://evoetxfjmkkjptucwxsv.supabase.co'
  );
end;
$function$;

revoke all on function public.nova_web_push_config_service() from public, anon, authenticated;
grant execute on function public.nova_web_push_config_service() to service_role;
