---
max_sentences: 6
max_chars: 900
min_chars: 150
forbid: overview, the following, in summary, —, "**"
forbid_opening: the output appears, here is, this section describes, based on the data provided
---
FORMAT: Report executive summary paragraph.

One flowing paragraph for the report's Section 1, read by non-experts first.
State: what was examined (artifact and event counts), what was found (finding
count with severity breakdown, grammatically correct singular/plural), the
single most significant finding by ID and title, and the overall risk level.

Rules:
- Open with what was examined, not a description of the data. Never begin with
  "The output appears", "Here is", "This section describes", or "Based on the
  data provided".
- Plain prose. No markdown, no bullets, no code formatting, no em-dashes.
- All timestamps as human dates (YYYY-MM-DD HH:MM), never epoch numbers.
- Every count, ID, title and score must be copied from the case data and must
  agree with the other numbers you state. Do not round, estimate, or supply a
  number the case data does not give.
- Attribute actions to accounts, never to named people.

SHAPE OF A CORRECT PARAGRAPH — structure only. Each bracketed item marks a slot
filled from the case data; never write a bracketed placeholder itself, and never
reuse a value from this example:

    This examination covered [COUNT] artifacts and interpreted [COUNT] events.
    The analysis produced [COUNT] critical findings, the most significant being
    [ID], [FINDING], which is a known technique for concealing data from normal
    file listings. The overall assessed risk is [LEVEL] ([COUNT]/100), driven by
    evidence consistent with deliberate concealment.

If the case produced no findings, say so directly and state the risk level as
the case data records it, rather than describing a finding that does not exist.
