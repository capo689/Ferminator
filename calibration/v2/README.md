# Ferminator Calibration V2

This frozen corpus captures Adam's human review of 61 Discover jobs on
2026-07-26:

- 11 Great
- 8 Maybe
- 40 Wrong
- 2 Duplicate

The source CSV is the verdict index. The source Markdown supplies the original
listing URL, complete job description, and long-form review. The build script
validates that job number, title, and company agree before emitting a record.

Rebuild intentionally:

```bash
python scripts/build_calibration_v2.py \
  --csv /path/to/discover-job-review-summary-2026-07-26.csv \
  --markdown /path/to/discover-full-jds-2026-07-26-reviewed.md \
  --output calibration/v2/corpus.jsonl
```

The checked-in SHA-256 in `ferminator.calibration_v2` makes silent edits fail.
The release gate requires 100% recall across the 19 Great/Maybe jobs and at
least 85% rejection of the reviewed Wrong jobs.
