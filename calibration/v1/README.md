# Ferminator Calibration V1

This is the frozen first scoring baseline. `corpus.jsonl` contains 58 historical
job reviews; `report.json` describes its coverage and `notes.md` defines the
multi-dimensional scoring architecture.

The corpus is immutable. Corrections and new human decisions belong in a later
version or an appended evaluation-event store. Ferminator verifies its SHA-256,
so accidental edits fail loudly.

V1 establishes regression evidence. It does not claim the current deterministic
matcher already reproduces every historical score; the limitations documented
in `notes.md` remain part of the baseline.
