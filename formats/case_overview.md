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

Structure, in order — include a clause only when the case data supports it, and
skip any that it does not:
1. When it happened and the anomalous trigger event (a time, a sign-in, a download).
2. What was done to the data, naming exact filenames, counts, and sizes.
3. Where the data went and what cleanup followed.
4. One clause noting any evidence of planning or intent, if present.

Rules:
- Open with what happened, not a description of the data. Never begin with
  "The output appears", "Here is", "This section describes", or "Based on the
  data provided".
- Past tense, neutral investigator voice. State only what the evidence shows.
- Name filenames and timestamps only where the case data gives them. If it
  gives none, write the paragraph without them and say what the case still
  lacks. Do not manufacture a filename or a time to satisfy the structure.
- Never speculate about motive or name a person as guilty; attribute actions to
  the account, not the human — "the <name> account", with <name> taken from the
  case data.

SHAPE OF A CORRECT PARAGRAPH — structure only. Each bracketed item marks a slot
filled from the case data; never write a bracketed placeholder itself, and never
reuse a value from this example:

    On [DATE], after an unusual [TIME] sign-in, [COUNT] files were gathered
    under [PATH], archived as [FILE] ([SIZE]), and copied to [DEVICE] at [TIME].
    Within [COUNT] minutes the local copies were deleted and [ARTIFACT] was
    cleared. Searches recorded the previous day bracket the sequence.

SHAPE WHEN THE CASE IS THINNER — equally correct, and preferable to invention:

    [COUNT] artifacts were parsed into [COUNT] events spanning [DATE] to [DATE].
    The activity recovered so far is routine filesystem and application use,
    with no account attribution available; nothing in the current artifacts
    establishes who was signed in.
