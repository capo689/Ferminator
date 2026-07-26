create table if not exists public.profile_role_thresholds (
  profile_id uuid not null references public.profiles(id) on delete cascade,
  family_id text not null check (family_id ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  threshold integer not null check (threshold between 0 and 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (profile_id, family_id)
);

alter table public.profile_role_thresholds enable row level security;
revoke all on public.profile_role_thresholds from anon, authenticated;
create policy "No direct client access"
  on public.profile_role_thresholds
  as restrictive
  for all
  to anon, authenticated
  using (false)
  with check (false);

comment on table public.profile_role_thresholds is
  'Server-managed per-profile visibility overrides for configured role families.';
