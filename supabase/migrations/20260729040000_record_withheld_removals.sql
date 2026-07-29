-- Record when a board's ingestion run tripped the mass-removal guard.
--
-- The guard blocks the delete but the run still finished successfully, so a
-- guarded run advanced the same clock expire_unseen_jobs() measures against and
-- executed the withheld deletion three days later. Recording the reason lets
-- expiry ignore runs that are not authoritative snapshots of the board.

alter table public.ingestion_runs
  add column if not exists removal_withheld text;

comment on column public.ingestion_runs.removal_withheld is
  'Reason the mass-removal guard withheld deletions, or null when the run is an '
  'authoritative snapshot. Expiry treats non-null runs as suspect.';

create index if not exists ingestion_runs_board_trust_idx
  on public.ingestion_runs (board_id, finished_at desc)
  where status = 'succeeded' and finished_at is not null;
