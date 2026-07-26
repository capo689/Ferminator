-- Search is performed against the compact in-memory NormalizedJob document.
-- With the duplicated persisted search document intentionally blank, this GIN
-- index has no live request path.
drop index if exists public.job_revisions_search_idx;
