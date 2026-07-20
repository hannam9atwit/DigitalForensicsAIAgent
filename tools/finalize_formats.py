"""
tools/finalize_formats.py

Promotes the AI format specs in formats/ from DRAFT to final, in place:
  1. Removes the "STATUS: DRAFT" line from each spec.
  2. Adds the report standard's hard rules to each spec's validation header
     (forbid em-dashes and markdown bold markers), so violations are caught
     at generation time and fed back to the model for a rewrite.

Idempotent: safe to run any number of times. Run from the repo root:

    python tools\\finalize_formats.py
"""

import glob
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMATS_DIR = os.path.join(REPO_ROOT, "formats")

EXTRA_FORBIDS = ["—", '"**"']


def finalize(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as spec_file:
        original = spec_file.read()

    updated = re.sub(r"STATUS: DRAFT[^\n]*\n", "", original)

    def extend_forbid_line(match):
        line = match.group(0).rstrip("\n")
        additions = [item for item in EXTRA_FORBIDS if item not in line]
        if additions:
            line += ", " + ", ".join(additions)
        return line + "\n"

    if re.search(r"^forbid:.*$", updated, re.MULTILINE):
        updated = re.sub(r"^forbid:.*\n", extend_forbid_line, updated,
                         count=1, flags=re.MULTILINE)
    else:
        updated = updated.replace(
            "---\n", "---\nforbid: " + ", ".join(EXTRA_FORBIDS) + "\n", 1)

    changes = []
    if "STATUS: DRAFT" in original:
        changes.append("draft marker removed")
    if updated != original and not changes:
        changes.append("validation rules added")
    elif updated != original:
        changes.append("validation rules added")

    if updated != original:
        with open(path, "w", encoding="utf-8") as spec_file:
            spec_file.write(updated)
    return changes


def main() -> int:
    spec_paths = sorted(glob.glob(os.path.join(FORMATS_DIR, "*.md")))
    if not spec_paths:
        print(f"[!] No spec files found in {FORMATS_DIR} — run from the repo.")
        return 1

    for path in spec_paths:
        changes = finalize(path)
        name = os.path.basename(path)
        print(f"[+] {name}: {', '.join(changes) if changes else 'already final'}")

    remaining = [os.path.basename(p) for p in spec_paths
                 if "STATUS: DRAFT" in open(p, encoding="utf-8").read()]
    if remaining:
        print(f"[!] Still marked draft: {', '.join(remaining)}")
        return 1

    print(f"\n[✓] All {len(spec_paths)} format specs are final.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
