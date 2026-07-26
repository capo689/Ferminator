alter table public.match_feedback
  add constraint match_feedback_profile_version_revision_key
  unique (profile_id, job_id, profile_version, job_revision_id);
