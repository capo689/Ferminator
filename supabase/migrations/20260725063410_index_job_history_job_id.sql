create index job_history_job_id_idx
  on public.job_history (job_id)
  where job_id is not null;
