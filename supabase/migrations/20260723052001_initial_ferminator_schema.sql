create extension if not exists pg_trgm with schema extensions;

create type public.ats_provider as enum (
  'greenhouse',
  'lever',
  'ashby',
  'smartrecruiters',
  'workable',
  'bamboohr'
);

create type public.run_status as enum (
  'queued',
  'running',
  'succeeded',
  'partial',
  'failed',
  'skipped'
);

create type public.pipeline_state as enum (
  'considering',
  'preparing',
  'applied',
  'interviewing',
  'offer',
  'closed',
  'dismissed'
);

create type public.notification_status as enum (
  'pending',
  'sent',
  'failed',
  'skipped'
);

create table public.profiles (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid unique references auth.users(id) on delete set null,
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  display_name text not null,
  email text,
  source_path text not null unique,
  source_hash text not null,
  profile_version integer not null default 1 check (profile_version > 0),
  scan_interval_hours integer not null default 12
    check (scan_interval_hours between 1 and 168),
  scan_enabled boolean not null default true,
  compiled_profile jsonb not null default '{}'::jsonb,
  last_scanned_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.companies (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,126}$'),
  name text not null,
  website_url text,
  career_url text,
  enabled boolean not null default true,
  priority smallint not null default 0 check (priority between -100 and 100),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.ats_boards (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id) on delete cascade,
  provider public.ats_provider not null,
  board_key text not null,
  region text not null default 'global',
  source_url text not null,
  enabled boolean not null default true,
  validation_status text not null default 'pending'
    check (validation_status in ('pending', 'healthy', 'degraded', 'failed', 'disabled')),
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  last_validated_at timestamptz,
  last_success_at timestamptz,
  last_error_code text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, board_key, region)
);

create table public.ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  board_id uuid references public.ats_boards(id) on delete set null,
  provider public.ats_provider not null,
  idempotency_key text not null unique,
  status public.run_status not null default 'queued',
  started_at timestamptz,
  finished_at timestamptz,
  fetched_count integer not null default 0 check (fetched_count >= 0),
  inserted_count integer not null default 0 check (inserted_count >= 0),
  updated_count integer not null default 0 check (updated_count >= 0),
  removed_count integer not null default 0 check (removed_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  request_count integer not null default 0 check (request_count >= 0),
  retry_count integer not null default 0 check (retry_count >= 0),
  duration_ms integer check (duration_ms is null or duration_ms >= 0),
  error_code text,
  error_message text,
  metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  ats_board_id uuid not null references public.ats_boards(id) on delete cascade,
  source_job_id text not null,
  source_key text not null unique,
  company_name text not null,
  title text not null,
  department text,
  team text,
  employment_type text,
  seniority text,
  workplace_type text,
  salary_min numeric(14, 2),
  salary_max numeric(14, 2),
  salary_currency char(3),
  salary_interval text,
  job_url text not null,
  apply_url text,
  published_at timestamptz,
  source_updated_at timestamptz,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  active boolean not null default true,
  removed_at timestamptz,
  current_revision_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (ats_board_id, source_job_id),
  check (salary_min is null or salary_min >= 0),
  check (salary_max is null or salary_max >= 0),
  check (salary_min is null or salary_max is null or salary_min <= salary_max)
);

create table public.job_revisions (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs(id) on delete cascade,
  content_hash text not null,
  description_text text not null default '',
  description_html text,
  search_document text not null default '',
  search_vector tsvector generated always as (
    to_tsvector('english', search_document)
  ) stored,
  normalized_payload jsonb not null,
  observed_at timestamptz not null default now(),
  unique (job_id, content_hash)
);

alter table public.jobs
  add constraint jobs_current_revision_fk
  foreign key (current_revision_id)
  references public.job_revisions(id)
  on delete set null;

create table public.job_locations (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs(id) on delete cascade,
  label text not null,
  city text,
  region text,
  country text,
  country_code char(2),
  is_primary boolean not null default false,
  is_remote boolean not null default false,
  normalized_key text not null,
  unique (job_id, normalized_key)
);

create table public.job_matches (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  job_revision_id uuid not null references public.job_revisions(id) on delete cascade,
  profile_version integer not null check (profile_version > 0),
  eligible boolean not null,
  score numeric(5, 2) not null check (score between 0 and 100),
  component_scores jsonb not null default '{}'::jsonb,
  matched_evidence jsonb not null default '[]'::jsonb,
  concerns jsonb not null default '[]'::jsonb,
  explanation text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, job_id, profile_version, job_revision_id)
);

create table public.job_actions (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  state public.pipeline_state not null default 'considering',
  priority smallint not null default 0 check (priority between -10 and 10),
  notes text not null default '',
  follow_up_at timestamptz,
  applied_at timestamptz,
  closed_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, job_id)
);

create table public.action_events (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  action_id uuid references public.job_actions(id) on delete set null,
  event_type text not null,
  from_state public.pipeline_state,
  to_state public.pipeline_state,
  note text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.saved_searches (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  name text not null,
  query text not null default '',
  filters jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, name)
);

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  channel text not null check (channel in ('email', 'dashboard')),
  notification_type text not null,
  idempotency_key text not null unique,
  status public.notification_status not null default 'pending',
  subject text,
  payload jsonb not null default '{}'::jsonb,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  last_error_code text,
  scheduled_for timestamptz,
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index profiles_auth_user_id_idx on public.profiles(auth_user_id);
create index ats_boards_enabled_idx on public.ats_boards(provider, enabled)
  where enabled;
create index jobs_active_last_seen_idx on public.jobs(last_seen_at desc)
  where active;
create index jobs_board_active_idx on public.jobs(ats_board_id, active);
create index jobs_title_trgm_idx on public.jobs
  using gin (title gin_trgm_ops);
create index jobs_company_trgm_idx on public.jobs
  using gin (company_name gin_trgm_ops);
create index job_revisions_search_idx on public.job_revisions
  using gin (search_vector);
create index job_locations_job_idx on public.job_locations(job_id);
create index job_matches_profile_score_idx on public.job_matches(profile_id, score desc)
  where eligible;
create index job_actions_profile_state_idx on public.job_actions(profile_id, state);
create index job_actions_follow_up_idx on public.job_actions(follow_up_at)
  where follow_up_at is not null;
create index action_events_profile_created_idx
  on public.action_events(profile_id, created_at desc);
create index notifications_pending_idx on public.notifications(scheduled_for)
  where status = 'pending';
create index ingestion_runs_provider_created_idx
  on public.ingestion_runs(provider, created_at desc);

alter table public.profiles enable row level security;
alter table public.companies enable row level security;
alter table public.ats_boards enable row level security;
alter table public.ingestion_runs enable row level security;
alter table public.jobs enable row level security;
alter table public.job_revisions enable row level security;
alter table public.job_locations enable row level security;
alter table public.job_matches enable row level security;
alter table public.job_actions enable row level security;
alter table public.action_events enable row level security;
alter table public.saved_searches enable row level security;
alter table public.notifications enable row level security;

create policy "profiles_select_own"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = auth_user_id);

create policy "authenticated_read_companies"
  on public.companies for select
  to authenticated
  using (true);

create policy "authenticated_read_boards"
  on public.ats_boards for select
  to authenticated
  using (true);

create policy "authenticated_read_jobs"
  on public.jobs for select
  to authenticated
  using (true);

create policy "authenticated_read_job_revisions"
  on public.job_revisions for select
  to authenticated
  using (true);

create policy "authenticated_read_job_locations"
  on public.job_locations for select
  to authenticated
  using (true);

create policy "matches_select_own"
  on public.job_matches for select
  to authenticated
  using (
    exists (
      select 1
      from public.profiles p
      where p.id = job_matches.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "actions_select_own"
  on public.job_actions for select
  to authenticated
  using (
    exists (
      select 1
      from public.profiles p
      where p.id = job_actions.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "actions_insert_own"
  on public.job_actions for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.profiles p
      where p.id = job_actions.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "actions_update_own"
  on public.job_actions for update
  to authenticated
  using (
    exists (
      select 1
      from public.profiles p
      where p.id = job_actions.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.profiles p
      where p.id = job_actions.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "actions_delete_own"
  on public.job_actions for delete
  to authenticated
  using (
    exists (
      select 1
      from public.profiles p
      where p.id = job_actions.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "events_select_own"
  on public.action_events for select
  to authenticated
  using (
    exists (
      select 1
      from public.profiles p
      where p.id = action_events.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "events_insert_own"
  on public.action_events for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.profiles p
      where p.id = action_events.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "saved_searches_manage_own"
  on public.saved_searches for all
  to authenticated
  using (
    exists (
      select 1
      from public.profiles p
      where p.id = saved_searches.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.profiles p
      where p.id = saved_searches.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

create policy "notifications_select_own"
  on public.notifications for select
  to authenticated
  using (
    exists (
      select 1
      from public.profiles p
      where p.id = notifications.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

revoke all on public.ingestion_runs from anon, authenticated;
revoke insert, update, delete on public.profiles from anon, authenticated;
revoke insert, update, delete on public.companies from anon, authenticated;
revoke insert, update, delete on public.ats_boards from anon, authenticated;
revoke insert, update, delete on public.jobs from anon, authenticated;
revoke insert, update, delete on public.job_revisions from anon, authenticated;
revoke insert, update, delete on public.job_locations from anon, authenticated;
revoke insert, update, delete on public.job_matches from anon, authenticated;
revoke insert, update, delete on public.notifications from anon, authenticated;
