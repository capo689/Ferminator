alter table public.match_feedback
  add column wrong_reason_code text;

update public.match_feedback
set wrong_reason_code = 'legacy_unspecified'
where verdict = 'wrong';

alter table public.match_feedback
  add constraint match_feedback_wrong_reason_code_check
  check (
    (
      verdict = 'wrong'
      and wrong_reason_code in (
        'legacy_unspecified',
        'function_mismatch',
        'too_technical',
        'seniority_mismatch',
        'qualification_gap',
        'domain_mismatch',
        'location_mismatch',
        'compensation_mismatch',
        'company_mismatch',
        'misleading_listing',
        'not_interested',
        'other'
      )
    )
    or (verdict <> 'wrong' and wrong_reason_code is null)
  );

alter table public.match_feedback_events
  add column wrong_reason_code text,
  add column reason text;

alter table public.match_feedback_events
  add constraint match_feedback_events_wrong_reason_code_check
  check (
    wrong_reason_code is null
    or wrong_reason_code in (
      'legacy_unspecified',
      'function_mismatch',
      'too_technical',
      'seniority_mismatch',
      'qualification_gap',
      'domain_mismatch',
      'location_mismatch',
      'compensation_mismatch',
      'company_mismatch',
      'misleading_listing',
      'not_interested',
      'other'
    )
  );

create index match_feedback_profile_wrong_reason_idx
  on public.match_feedback(profile_id, wrong_reason_code)
  where verdict = 'wrong';
