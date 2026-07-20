---
max_sentences: 6
max_chars: 900
min_chars: 150
forbid: overview, the following, in summary
---
FORMAT: Report executive summary paragraph.
STATUS: DRAFT — replace this file with the finalized format when approved.

One flowing paragraph for the report's Section 1, read by non-experts first.
State: what was examined (artifact and event counts), what was found (finding
count with severity breakdown, grammatically correct singular/plural), the
single most significant finding by ID and title, and the overall risk level.

Rules:
- Plain prose. No markdown, no bullets, no code formatting, no em-dashes.
- All timestamps as human dates (2026-06-03 19:18), never epoch numbers.
- Numbers must match the case data exactly and agree with each other.
- Attribute actions to accounts, never to named people.

EXAMPLE OF CORRECT OUTPUT:
This examination covered one disk image and interpreted 38 events. The
analysis produced one critical finding: an abnormal $BadClus stream of
516,554,240 bytes, a known location for concealing data from normal file
listings. The overall assessed risk is high (72/100), driven by evidence
consistent with deliberate concealment.
