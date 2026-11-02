-- Explicitly assigned website accounts may submit station entries.
alter table public.website_member_roles
  drop constraint if exists website_member_roles_role_check;
alter table public.website_member_roles
  add constraint website_member_roles_role_check
  check (role in ('super_admin', 'admin', 'manager', 'member', 'staff'));

create table if not exists public.website_entry_submissions (
  entry_id uuid primary key default gen_random_uuid(),
  member_id uuid not null references auth.users(id) on delete restrict,
  member_email text not null,
  entry_type text not null check (entry_type in ('pump_session', 'fuel_receipt', 'account_activity', 'tank_dip')),
  payload jsonb not null,
  status text not null default 'pending' check (status in ('pending', 'accepted', 'rejected')),
  created_at timestamptz not null default now(),
  processed_at timestamptz,
  processing_note text
);

create index if not exists website_entry_submissions_pending_idx
  on public.website_entry_submissions (created_at)
  where status = 'pending';

alter table public.website_entry_submissions enable row level security;
revoke all on table public.website_entry_submissions from public, anon, authenticated;

-- Assign staff access only to the intended website user after creating their
-- Supabase Auth account. Replace the email with the specific staff account.
-- insert into public.website_member_roles (user_id, role, active)
-- select id, 'staff', true from auth.users
-- where lower(email) = lower('assigned.operator@example.com')
-- on conflict (user_id) do update set role = excluded.role, active = true;
