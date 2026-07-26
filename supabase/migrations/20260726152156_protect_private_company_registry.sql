-- The curated company/ATS registry is server-private product data.
-- The application and scheduled scanner connect directly to Postgres with a
-- protected server credential. Browser/API roles do not need table access.

drop policy if exists "authenticated_read_companies" on public.companies;
drop policy if exists "authenticated_read_boards" on public.ats_boards;

revoke all privileges on table public.companies from anon, authenticated;
revoke all privileges on table public.ats_boards from anon, authenticated;
