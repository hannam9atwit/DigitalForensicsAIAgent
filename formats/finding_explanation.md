---
max_sentences: 5
max_chars: 700
min_chars: 100
forbid: this finding, as mentioned, technical term, —, "**"
forbid_opening: the output appears, here is, this section describes, based on the data provided
---
FORMAT: Per-finding plain-language explanation ("What was found").

A short paragraph a non-expert understands: what was found, in normal words,
and why it matters in this case. The technical detail lives in a separate
field; do not put artifact mechanics here.

Rules:
- Open with what was found, not a description of the data. Never begin with
  "The output appears", "Here is", "This section describes", or "Based on the
  data provided".
- Everyday language; translate any necessary term immediately.
- Use the numbers, filenames and times carried by THIS finding, written in
  human-readable form. Where the finding does not carry one, leave it out; do
  not supply a filename, account or time the finding does not record.
- No markdown, no em-dashes, no speculation about motive.
