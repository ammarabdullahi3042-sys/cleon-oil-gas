-- CLEON contact inbox: least-privilege access for public submissions and admins.
-- Run this in Supabase SQL Editor after creating contact_messages and an Auth user.

alter table public.contact_messages
  add column if not exists created_at timestamptz not null default now();

create table if not exists public.cleon_admins (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

alter table public.cleon_admins enable row level security;
revoke all on table public.cleon_admins from public, anon, authenticated;

create or replace function public.is_cleon_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.cleon_admins
    where user_id = (select auth.uid())
  );
$$;

revoke all on function public.is_cleon_admin() from public, anon;
grant execute on function public.is_cleon_admin() to authenticated;

alter table public.contact_messages enable row level security;
revoke all on table public.contact_messages from public, anon, authenticated;
grant usage on schema public to anon, authenticated;
grant insert on table public.contact_messages to anon;
grant select on table public.contact_messages to authenticated;

drop policy if exists "Allow public contact submissions" on public.contact_messages;
create policy "Allow public contact submissions"
  on public.contact_messages
  for insert
  to anon
  with check (true);

drop policy if exists "CLEON admins can read contact submissions" on public.contact_messages;
drop policy if exists "Authenticated users may request contact submissions" on public.contact_messages;
create policy "Authenticated users may request contact submissions"
  on public.contact_messages
  for select
  to authenticated
  using (true);

create policy "CLEON admins can read contact submissions"
  on public.contact_messages
  as restrictive
  for select
  to authenticated
  using ((select public.is_cleon_admin()));

-- Grant the table's identity/serial sequence to public submitters when one exists.
do $$
declare
  sequence_name text := pg_get_serial_sequence('public.contact_messages', 'id');
begin
  if sequence_name is not null then
    execute format('revoke all on sequence %s from public, anon, authenticated', sequence_name);
    execute format('grant usage, select on sequence %s to anon', sequence_name);
  end if;
end;
$$;

-- After creating your admin user in Authentication > Users, replace the email below
-- and run this separately to allow that account to view submissions.
-- insert into public.cleon_admins (user_id)
-- select id from auth.users where lower(email) = lower('admin@example.com')
-- on conflict (user_id) do nothing;
