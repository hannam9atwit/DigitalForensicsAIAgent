---
max_sentences: 6
max_chars: 800
min_chars: 120
forbid: in conclusion, to conclude, wrapping up, —, "**"
forbid_opening: the output appears, here is, this section describes, based on the data provided
---
FORMAT: Report conclusion narrative.

A few sentences giving the examiner's overall read: what the evidence
collectively suggests, how the findings relate, and the confidence in that
assessment with its basis. Written for examiner review.

Rules:
- Open with the overall read of the evidence, never with meta-commentary
  ("The output appears", "Here is", "This section describes", "Based on the
  data provided").
- Calibrated language: "consistent with", "indicates", never certainty the
  evidence doesn't support.
- Reference finding IDs when anchoring claims, using only IDs present in the
  supplied case data.
- Name an account, file, device or time only where the case data establishes
  it. Where the picture is incomplete, state what remains unestablished — a
  conclusion that names its own gaps is stronger than one that fills them.
- No markdown, no em-dashes. Do not restate every finding; synthesize.
