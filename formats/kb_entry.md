---
min_chars: 30
max_chars: 700
forbid: json, array, the data provided, i cannot, as an ai
forbid_opening: the output appears, here is, this section describes, based on the data provided
---
FORMAT: One knowledge-base finding.

You are digesting evidence into a single, reusable analytical finding that a
later step (and the examiner) will read and cite. Answer the one question you
are given about the material provided, and nothing else.

Rules:
- Two to four sentences of plain investigator prose. No headings, no lists, no
  markdown.
- State a conclusion, then its basis. Lead with what the evidence shows, never
  with a description of the data or the task.
- Use only the material provided for this question — do not invent artifacts,
  counts, times, or names that are not present.
- Name exact values (hosts, paths, counts, timestamps) when the material has
  them; they are what makes the finding citable.
- Calibrate confidence in words ("consistent with", "indicates", "suggests");
  do not overstate what the evidence supports.
- If the material does not answer the question, say so plainly in one sentence
  and name what would answer it. An honest gap is a valid finding.

EXAMPLE OF CORRECT OUTPUT:
Traffic is dominated by sustained TCP sessions from 10.0.0.14 to the external
host 93.184.216.34 on port 443, accounting for most of the capture's volume.
The one-directional weighting toward the external host is consistent with data
leaving the network rather than routine browsing, and the sessions cluster in a
single 40-minute window on 2026-06-03.
