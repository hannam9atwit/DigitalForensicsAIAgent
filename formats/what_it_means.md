---
max_sentences: 2
max_chars: 260
min_chars: 30
forbid: this event, this row, the data shows, —, "**"
forbid_opening: the output appears, here is, this section describes, based on the data provided
---
FORMAT: Evidence / timeline "what it means" note.

You are writing the 1-2 sentence interpretation shown next to a single
artifact or timeline event. State what the artifact tells the investigation —
a forensic conclusion, not a description of the record.

Rules:
- Lead with the conclusion, not the artifact type — and never with
  meta-commentary ("The output appears", "Here is", "This section describes",
  "Based on the data provided").
- If the artifact is routine system noise, say so plainly and why.
- Name the significance tier implicitly through word choice — "planning
  indicator", "routine", "central event" — never as a label.
- Say only what the supplied artifact facts support. If they do not establish
  an account, a device or a time, do not name one.

SHAPE OF A CORRECT NOTE — structure only. Each bracketed item marks a slot
filled from the supplied facts; never write a bracketed placeholder itself, and
never reuse a value from this example:

    Research into [TOPIC], a planning indicator recorded the day before the
    incident.

SHAPE FOR A ROUTINE RECORD:

    Routine operating-system housekeeping, written automatically and not tied to
    user action.
