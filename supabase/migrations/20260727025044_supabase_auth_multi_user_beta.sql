-- Native Supabase Auth is the identity provider for the five-user beta.
-- Existing profile ownership already uses profiles.auth_user_id and auth.uid().

alter table public.profiles
  add column onboarding_markdown text,
  add column onboarding_schema_version integer not null default 1
    check (onboarding_schema_version > 0);

create table public.accounts (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid not null unique references auth.users(id) on delete restrict,
  profile_id uuid unique references public.profiles(id) on delete restrict,
  username text not null unique check (username ~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{2,31}$'),
  email text not null,
  role text not null default 'user' check (role in ('user', 'sysadmin')),
  status text not null default 'pending'
    check (status in ('pending', 'provisioning', 'active', 'suspended', 'failed')),
  feature_flags jsonb not null default '{}'::jsonb,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (role = 'sysadmin' and profile_id is null)
    or (role = 'user' and profile_id is not null)
  )
);

create unique index accounts_single_sysadmin_idx
  on public.accounts (role)
  where role = 'sysadmin';

create or replace function public.enforce_beta_user_limit()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.role = 'user' then
    perform pg_advisory_xact_lock(hashtextextended('ferminator:beta-user-limit', 0));
    if (select count(*) from public.accounts where role = 'user') >= 5 then
      raise exception 'Ferminator beta is limited to five user accounts'
        using errcode = 'check_violation';
    end if;
  end if;
  return new;
end;
$$;

create trigger accounts_enforce_beta_user_limit
before insert on public.accounts
for each row execute function public.enforce_beta_user_limit();

create table public.account_schedules (
  account_id uuid primary key references public.accounts(id) on delete cascade,
  timezone text not null default 'America/Los_Angeles',
  run_times time[] not null default array['08:00'::time, '16:00'::time],
  enabled boolean not null default true,
  next_run_at timestamptz,
  updated_at timestamptz not null default now(),
  check (cardinality(run_times) between 1 and 4)
);

create table public.matching_run_queue (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  requested_by uuid references public.accounts(id) on delete set null,
  reason text not null check (reason in ('onboarding', 'scheduled', 'manual', 'profile_update')),
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  summary jsonb not null default '{}'::jsonb,
  error_code text,
  error_detail text,
  check (
    (status = 'queued' and started_at is null and finished_at is null)
    or (status = 'running' and started_at is not null and finished_at is null)
    or (status in ('succeeded', 'failed', 'cancelled') and finished_at is not null)
  )
);

create unique index matching_run_queue_one_active_per_account_idx
  on public.matching_run_queue(account_id)
  where status in ('queued', 'running');
create index matching_run_queue_status_requested_idx
  on public.matching_run_queue(status, requested_at);

create table public.admin_audit_events (
  id bigint generated always as identity primary key,
  actor_account_id uuid references public.accounts(id) on delete set null,
  target_account_id uuid references public.accounts(id) on delete set null,
  action text not null,
  request_id text,
  before_state jsonb,
  after_state jsonb,
  created_at timestamptz not null default now()
);

create index admin_audit_events_created_idx
  on public.admin_audit_events(created_at desc);
create index admin_audit_events_target_created_idx
  on public.admin_audit_events(target_account_id, created_at desc);

alter table public.accounts enable row level security;
alter table public.account_schedules enable row level security;
alter table public.matching_run_queue enable row level security;
alter table public.admin_audit_events enable row level security;

-- Account roles and the administrative control plane are server-managed.
revoke all on public.accounts from anon, authenticated;
revoke all on public.account_schedules from anon, authenticated;
revoke all on public.matching_run_queue from anon, authenticated;
revoke all on public.admin_audit_events from anon, authenticated;

comment on table public.accounts is
  'Server-managed Supabase Auth bindings and beta roles. Client metadata is never authoritative.';
comment on table public.admin_audit_events is
  'Append-only audit history for administrative control-plane mutations.';
