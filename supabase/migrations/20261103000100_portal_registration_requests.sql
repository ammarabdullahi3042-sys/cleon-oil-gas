create table if not exists public.website_registration_requests (
  request_id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  full_name text not null,
  requested_role text not null check (requested_role in ('member', 'staff', 'admin')),
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  reviewed_by uuid references auth.users(id)
);
alter table public.website_registration_requests enable row level security;
revoke all on public.website_registration_requests from public, anon, authenticated;
