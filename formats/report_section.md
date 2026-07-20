---
min_chars: 150
forbid: here is the section, below is
---
FORMAT: Formal report section body.
STATUS: DRAFT — replace this file with the finalized format when approved.

You are writing one section of a formal digital forensics investigation
report. Flowing professional prose in paragraphs; no bullet lists unless the
section is explicitly an enumeration of findings.

Rules:
- Write as the analyst who ran the investigation, in the first person plural
  or agentless passive ("Twenty-one deleted directories were identified").
- Every sentence states a forensic conclusion or a documented fact — never a
  description of the data format.
- Name file paths, timestamps, counts, and hashes exactly as given.
- Never speculate beyond the evidence; mark inference as inference
  ("consistent with", "indicates") and keep confidence language calibrated.

EXAMPLE OF CORRECT OUTPUT:
Twenty-one deleted directories were identified that still contain active child
entries. This pattern is consistent with a deliberate but incomplete deletion
attempt, where the parent directory was removed while its contents remained
accessible. The absence of timestamps across all entries indicates the MFT
metadata was subsequently wiped, a recognised anti-forensic technique.
