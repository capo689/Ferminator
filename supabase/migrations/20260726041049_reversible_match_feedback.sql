alter table public.match_feedback
  drop constraint match_feedback_verdict_check,
  add constraint match_feedback_verdict_check
    check (verdict in ('great', 'maybe', 'wrong', 'duplicate'));

with ranked as (
  select id, row_number() over (
    partition by profile_id, job_id
    order by updated_at desc, created_at desc, id desc
  ) as position
  from public.match_feedback
)
delete from public.match_feedback f
using ranked r
where f.id = r.id and r.position > 1;

alter table public.match_feedback
  drop constraint match_feedback_profile_id_job_id_profile_version_job_revisi_key,
  add constraint match_feedback_profile_job_key unique (profile_id, job_id);

create table public.match_feedback_events (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  action text not null check (action in ('set', 'cleared')),
  prior_verdict text check (
    prior_verdict is null
    or prior_verdict in ('great', 'maybe', 'wrong', 'duplicate')
  ),
  verdict text check (
    verdict is null
    or verdict in ('great', 'maybe', 'wrong', 'duplicate')
  ),
  created_at timestamptz not null default now(),
  check (
    (action = 'set' and verdict is not null)
    or (action = 'cleared' and verdict is null and prior_verdict is not null)
  )
);

create index match_feedback_events_profile_created_idx
  on public.match_feedback_events(profile_id, created_at desc);
create index match_feedback_events_job_idx
  on public.match_feedback_events(job_id);

alter table public.match_feedback_events enable row level security;

create policy "match_feedback_events_select_own"
  on public.match_feedback_events for select
  to authenticated
  using (
    exists (
      select 1 from public.profiles p
      where p.id = match_feedback_events.profile_id
        and p.auth_user_id = (select auth.uid())
    )
  );

revoke insert, update, delete
  on public.match_feedback_events from anon, authenticated;
