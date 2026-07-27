create policy "accounts_deny_direct_client_access"
  on public.accounts
  as restrictive for all to anon, authenticated
  using (false) with check (false);

create policy "account_schedules_deny_direct_client_access"
  on public.account_schedules
  as restrictive for all to anon, authenticated
  using (false) with check (false);

create policy "matching_run_queue_deny_direct_client_access"
  on public.matching_run_queue
  as restrictive for all to anon, authenticated
  using (false) with check (false);

create policy "admin_audit_events_deny_direct_client_access"
  on public.admin_audit_events
  as restrictive for all to anon, authenticated
  using (false) with check (false);

create index matching_run_queue_requested_by_idx
  on public.matching_run_queue(requested_by)
  where requested_by is not null;

create index admin_audit_events_actor_created_idx
  on public.admin_audit_events(actor_account_id, created_at desc)
  where actor_account_id is not null;
