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
- Use ONLY the MATERIAL supplied with this question. Every host, address, path,
  filename, account and timestamp you write must appear in that material. Do not
  invent artifacts, counts, times or names, and do not carry values over from
  another artifact or another question.
- Name exact values when the material has them; they are what makes the finding
  citable.
- Calibrate confidence in words ("consistent with", "indicates", "suggests");
  do not overstate what the evidence supports.
- If the material does not answer the question, say so plainly in one sentence
  and name what would answer it. An honest gap is a valid, useful finding.

SHAPE OF A CORRECT FINDING — structure only. Each bracketed item marks a slot
filled from the MATERIAL; never write a bracketed placeholder itself, and never
reuse a value from this example:

    Traffic is dominated by sustained [PROTOCOL] sessions from [HOST] to the
    external host [HOST] on port [COUNT], accounting for most of the capture's
    volume. The one-directional weighting toward the external host is consistent
    with data leaving the network rather than routine browsing, and the sessions
    cluster in a single window on [DATE].

SHAPE OF A CORRECT GAP — equally valid:

    The material does not establish which account this activity belongs to: the
    records carry paths and timestamps but no account attribution. A registry
    hive or a Security event log from the same host would establish it.
