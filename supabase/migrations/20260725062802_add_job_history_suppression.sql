create function public.normalize_job_part(value text)
returns text
language sql
immutable
parallel safe
returns null on null input
set search_path = ''
as $$
  select trim(regexp_replace(
    regexp_replace(
      regexp_replace(
        regexp_replace(lower(replace(value, '&', ' and ')), '\([^)]*\)', ' ', 'g'),
        '[®™©]', '', 'g'
      ),
      '[^a-z0-9]+', ' ', 'g'
    ),
    '\s+', ' ', 'g'
  ))
$$;

create table public.job_history (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  job_id uuid references public.jobs(id) on delete set null,
  company_name text not null,
  title text not null,
  normalized_company text not null,
  normalized_title text not null,
  fingerprint text not null,
  category text not null,
  status text not null,
  source text not null default 'dashboard',
  source_job_key text,
  first_recorded_at timestamptz not null default now(),
  applied_at timestamptz,
  suppress_until timestamptz,
  permanent boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, fingerprint)
);

create table public.company_watchlist (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  company_name text not null,
  normalized_company text not null,
  note text not null default 'Prior application at this company — confirm not a duplicate.',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, normalized_company)
);

create index job_history_profile_suppression_idx
  on public.job_history (profile_id, fingerprint, suppress_until);
create unique index job_history_profile_source_key_idx
  on public.job_history (profile_id, source_job_key)
  where source_job_key is not null;
create index company_watchlist_profile_company_idx
  on public.company_watchlist (profile_id, normalized_company);

alter table public.job_history enable row level security;
alter table public.company_watchlist enable row level security;

create policy "job_history_select_own"
  on public.job_history for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = job_history.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "company_watchlist_select_own"
  on public.company_watchlist for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = company_watchlist.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );
