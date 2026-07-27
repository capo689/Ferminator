# Ferminator Calibration V3

This frozen corpus combines Adam's two complete Discover review batches from
July 26, 2026:

- 13 Great
- 13 Maybe
- 57 Wrong
- 2 Duplicate
- 85 total reviewed jobs

The V3 release gate requires 100% recall across all 26 Great/Maybe jobs and
100% rejection of the 57 reviewed Wrong jobs. The complete JDs and long-form
human reviews are retained so future matcher changes can be evaluated against
the actual requirements rather than title-only fixtures.

Rebuild intentionally:

```bash
python scripts/build_calibration_v3.py \
  --base calibration/v2/corpus.jsonl \
  --csv /path/to/discover-unrated-job-review-summary-2026-07-26.csv \
  --markdown /path/to/discover-unrated-full-jds-2026-07-26-reviewed.md \
  --output calibration/v3/corpus.jsonl
```

The SHA-256 stored in `ferminator.calibration_v3` prevents silent corpus edits.
