-- Single-user alpha reliability, quality feedback, and scan-level observability.

create table public.scan_runs (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  status public.run_status not null default 'running',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  board_count integer not null default 0 check (board_count >= 0),
  succeeded_count integer not null default 0 check (succeeded_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  scored_job_count integer not null default 0 check (scored_job_count >= 0),
  error_codes jsonb not null default '[]'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (
    (status = 'running' and finished_at is null)
    or (status <> 'running' and finished_at is not null)
  )
);

create table public.match_feedback (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  job_revision_id uuid not null references public.job_revisions(id) on delete cascade,
  profile_version integer not null check (profile_version > 0),
  verdict text not null check (verdict in ('great', 'maybe', 'wrong')),
  reason text,
  score_at_feedback numeric(5, 2) not null check (score_at_feedback between 0 and 100),
  component_scores jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, job_id, profile_version, job_revision_id)
);

create index scan_runs_started_idx on public.scan_runs(started_at desc);
create index scan_runs_failed_idx on public.scan_runs(started_at desc)
  where status = 'failed';
create index match_feedback_profile_created_idx
  on public.match_feedback(profile_id, created_at desc);
create index match_feedback_profile_verdict_idx
  on public.match_feedback(profile_id, verdict);

alter table public.scan_runs enable row level security;
alter table public.match_feedback enable row level security;

create policy "scan_runs_deny_client_access"
  on public.scan_runs for select
  to anon, authenticated
  using (false);

create policy "match_feedback_select_own"
  on public.match_feedback for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = match_feedback.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "match_feedback_insert_own"
  on public.match_feedback for insert
  to authenticated
  with check (
    exists (
      select 1 from public.profiles p
      where p.id = match_feedback.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "match_feedback_update_own"
  on public.match_feedback for update
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = match_feedback.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.profiles p
      where p.id = match_feedback.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

revoke all on public.scan_runs from anon, authenticated;
revoke insert, update, delete on public.match_feedback from anon, authenticated;
