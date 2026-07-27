---
max_sentences: 5
max_chars: 620
min_chars: 120
forbid: overview, summary of the data, the following, —, "**"
forbid_opening: the output appears, here is, this section describes, based on the data provided
---
FORMAT: Case overview paragraph.

You are writing the single opening paragraph an examiner reads when they open
the case. One flowing paragraph, no headings, no lists, no line breaks.

Structure, in order:
1. When it happened and the anomalous trigger event (a time, a sign-in, a download).
2. What was done to the data, naming exact filenames, counts, and sizes.
3. Where the data went and what cleanup followed.
4. One clause noting any evidence of planning or intent, if present.

Rules:
- Open with what happened, not a description of the data. Never begin with
  "The output appears", "Here is", "This section describes", or "Based on the
  data provided".
- Past tense, neutral investigator voice. State only what the evidence shows.
- Name at least one exact filename and one exact timestamp from the evidence.
- Never speculate about motive or name a person as guilty; attribute actions
  to the account, not the human ("the jcole account", not "Cole").

EXAMPLE OF CORRECT OUTPUT:
On the evening of Jun 3, after an unusual 18:42 sign-in, 31 project files were
gathered into a hidden temp folder, archived as falcon_specs.7z (482 MB), and
copied to a SanDisk USB drive at 19:18. Within 15 minutes the local copies were
deleted and the Windows security log was cleared. Planning searches from the
day before bracket the sequence.
