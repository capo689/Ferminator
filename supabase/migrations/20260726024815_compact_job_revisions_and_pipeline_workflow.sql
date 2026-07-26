-- Add an explicit non-destructive terminal state for jobs the user wants to
-- retain without keeping on the active campaign board.
alter type public.pipeline_state add value if not exists 'archived';

-- The plain-text description remains the canonical, copyable job description.
-- These other values duplicate it and account for most database storage.
-- Keep the columns during the alpha so application/database rollout order stays
-- backwards compatible; new application code writes compact values.
update public.job_revisions
set description_html = null,
    search_document = '',
    normalized_payload = normalized_payload
      - 'description_text'
      - 'description_html'
where description_html is not null
   or search_document <> ''
   or normalized_payload ? 'description_text'
   or normalized_payload ? 'description_html';

create index if not exists job_actions_profile_updated_idx
  on public.job_actions(profile_id, updated_at desc);

create index if not exists action_events_profile_job_created_idx
  on public.action_events(profile_id, job_id, created_at desc);
