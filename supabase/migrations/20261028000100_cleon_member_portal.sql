-- CLEON member portal storage and authorization.
-- The Edge Function uses the server-side service key; browser and desktop
-- clients receive only the publishable key and cannot access these tables.

create table if not exists public.website_member_roles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null check (role in ('super_admin', 'admin', 'manager', 'member')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.website_snapshots (
  section text primary key check (section in ('dashboard', 'reports')),
  payload jsonb not null,
  updated_at timestamptz not null default now(),
  published_at timestamptz not null
);

create table if not exists public.website_documents (
  document_id text primary key,
  filename text not null,
  content_type text not null,
  storage_path text not null unique,
  uploaded_at timestamptz not null default now()
);

alter table public.website_member_roles enable row level security;
alter table public.website_snapshots enable row level security;
alter table public.website_documents enable row level security;

revoke all on table public.website_member_roles from public, anon, authenticated;
revoke all on table public.website_snapshots from public, anon, authenticated;
revoke all on table public.website_documents from public, anon, authenticated;

-- Private files are served through the authorized Edge Function.
insert into storage.buckets (id, name, public, file_size_limit)
values ('cleon-website-documents', 'cleon-website-documents', false, 10485760)
on conflict (id) do update
set public = false, file_size_limit = 10485760;

-- Promote the already-verified CLEON owner account in the portal. This uses
-- the Auth user record; it does not create or change any password.
insert into public.website_member_roles (user_id, role, active)
select id, 'super_admin', true
from auth.users
where lower(email) = lower('ammarabdullahi3042@gmail.com')
limit 1
on conflict (user_id) do update
set role = excluded.role, active = true;

-- To add a member: create the account in Supabase Authentication > Users,
-- then add the role for that account with SQL like this:
-- insert into public.website_member_roles (user_id, role)
-- select id, 'member' from auth.users where lower(email) = lower('member@example.com')
-- on conflict (user_id) do update set role = excluded.role, active = true;
