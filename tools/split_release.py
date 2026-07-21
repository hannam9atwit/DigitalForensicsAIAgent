"""
tools/split_release.py

Splits the Full installer into numbered parts that fit under GitHub's 2 GiB
per-release-asset limit, and writes the exact rejoin instructions to include
in the release notes.

Usage (from the repo root, after build_windows.bat):

    python tools\\split_release.py

Produces in dist\\:
    AIRforensics_Setup-Full.exe.part1
    AIRforensics_Setup-Full.exe.part2
    REJOIN_INSTRUCTIONS.txt

Users rejoin with one built-in Windows command (no extra software):

    copy /b AIRforensics_Setup-Full.exe.part1 + AIRforensics_Setup-Full.exe.part2 AIRforensics_Setup-Full.exe

The split is a raw byte split, so the rejoined file is byte-identical to the
original; verify with the published SHA-256.
"""

import hashlib
import os
import sys

# 1900 MB per part: safely under GitHub's 2 GiB (2147 MB) asset cap.
PART_SIZE = 1900 * 1024 * 1024
CHUNK = 8 * 1024 * 1024

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO_ROOT, "dist", "AIRforensics_Setup-Full.exe")


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def split() -> int:
    if not os.path.isfile(SOURCE):
        print(f"[!] Not found: {SOURCE}")
        print("    Run build_windows.bat first.")
        return 1

    total_size = os.path.getsize(SOURCE)
    part_count = (total_size + PART_SIZE - 1) // PART_SIZE
    print(f"[*] {os.path.basename(SOURCE)}: "
          f"{total_size / 1_073_741_824:.2f} GB → {part_count} parts")

    print("[*] Hashing the original (this is the hash users verify against)...")
    original_hash = sha256_of(SOURCE)

    part_names = []
    with open(SOURCE, "rb") as source:
        for part_number in range(1, part_count + 1):
            part_path = f"{SOURCE}.part{part_number}"
            written = 0
            with open(part_path, "wb") as part:
                while written < PART_SIZE:
                    block = source.read(min(CHUNK, PART_SIZE - written))
                    if not block:
                        break
                    part.write(block)
                    written += len(block)
            size_mb = os.path.getsize(part_path) / 1_048_576
            print(f"[+] {os.path.basename(part_path)}: {size_mb:.0f} MB")
            part_names.append(os.path.basename(part_path))

    joined = " + ".join(part_names)
    instructions = (
        "AIRforensics Full installer - rejoin instructions\n"
        "==================================================\n\n"
        "1. Download every part below into the SAME folder.\n\n"
        "2. Open Command Prompt in that folder and run:\n\n"
        f"   copy /b {joined} AIRforensics_Setup-Full.exe\n\n"
        "3. (Recommended) Verify the rejoined file:\n\n"
        "   certutil -hashfile AIRforensics_Setup-Full.exe SHA256\n\n"
        f"   Expected SHA-256:\n   {original_hash}\n\n"
        "4. Run AIRforensics_Setup-Full.exe. The parts can be deleted after.\n"
    )
    instructions_path = os.path.join(REPO_ROOT, "dist",
                                     "REJOIN_INSTRUCTIONS.txt")
    with open(instructions_path, "w", encoding="ascii") as note:
        note.write(instructions)

    print(f"\n[+] Wrote {instructions_path}")
    print(f"[+] Original SHA-256: {original_hash}")
    print("\nPaste the rejoin block from REJOIN_INSTRUCTIONS.txt into the "
          "release notes,\nand upload the .part files as release assets.")
    return 0


if __name__ == "__main__":
    sys.exit(split())
