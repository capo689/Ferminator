-- Make the intentional server-only posture explicit to the database advisor.
create policy "ingestion_runs_deny_client_access"
  on public.ingestion_runs for select
  to anon, authenticated
  using (false);

-- Cover every foreign key used during cascading deletes and joins.
create index action_events_action_id_idx
  on public.action_events(action_id);
create index action_events_job_id_idx
  on public.action_events(job_id);
create index ats_boards_company_id_idx
  on public.ats_boards(company_id);
create index ingestion_runs_board_id_idx
  on public.ingestion_runs(board_id);
create index job_actions_job_id_idx
  on public.job_actions(job_id);
create index job_matches_job_id_idx
  on public.job_matches(job_id);
create index job_matches_revision_id_idx
  on public.job_matches(job_revision_id);
create index jobs_current_revision_id_idx
  on public.jobs(current_revision_id);
create index notifications_profile_id_idx
  on public.notifications(profile_id);
