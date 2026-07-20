"""
gui_v2/interpreter.py

The forensic knowledge layer. Turns raw parsed events into something an
examiner can actually read: a category, a plain-English description of what the
artifact IS, and why it matters (or doesn't).

The problem this solves: a raw disk timeline is mostly NTFS internal metadata
($MFT, $BadClus, $Bitmap …) that exists on every Windows volume and means
nothing on its own. Without interpretation every row looks the same. This
module:

  1. classifies each event (system_metadata / os_file / user_file / program /
     browser / registry / eventlog / network / email …)
  2. attaches a human description ("NTFS Master File Table — the index of every
     file on the volume; present on all NTFS disks")
  3. assigns a relevance so the UI can dim or hide noise and surface real
     activity
  4. fixes the "everything is LOW / identical timestamp" problem by deriving
     severity and notes from what the artifact actually is

It is pure data + functions: no Qt, no I/O, easy to unit test and extend.
"""

import re
import os

# ── relevance tiers ───────────────────────────────────────────────────────────
NOISE = "noise"            # NTFS internals, present on every volume
CONTEXT = "context"        # OS files / normal system activity
NOTABLE = "notable"        # user files, program execution, browser, etc.
SIGNIFICANT = "significant"  # deletions, USB, exfil, anti-forensics

RELEVANCE_RANK = {NOISE: 0, CONTEXT: 1, NOTABLE: 2, SIGNIFICANT: 3}


# ── NTFS system-metadata files (the noise in your screenshot) ─────────────────
# Each: short description of what the structure is.
NTFS_SYSTEM = {
    "$MFT": "Master File Table — the index of every file/folder on the volume.",
    "$MFTMirr": "Backup copy of the first MFT records, used for recovery.",
    "$LogFile": "NTFS transaction journal used to recover after a crash.",
    "$Volume": "Volume metadata: label, serial number, NTFS version.",
    "$AttrDef": "Definition table for the attribute types NTFS supports.",
    "$Bitmap": "Allocation bitmap marking which clusters are in use.",
    "$Boot": "Boot sector / bootstrap code for the volume.",
    "$BadClus": "List of clusters marked bad on the disk.",
    "$BadClus:$Bad": "Stream tracking bad clusters (can be abused to hide data).",
    "$Secure": "Central store of security descriptors (permissions) for files.",
    "$Secure:$SDS": "Security descriptor stream within $Secure.",
    "$UpCase": "Uppercase-conversion table for case-insensitive filenames.",
    "$Extend": "Container for optional NTFS extensions (quotas, object IDs).",
    "$Extend/$ObjId": "Object IDs used by the distributed link-tracking service.",
    "$Extend/$Quota": "Per-user disk quota records.",
    "$Extend/$Reparse": "Index of reparse points (junctions, symlinks).",
    "$Extend/$UsnJrnl": "USN change journal — a log of file changes (forensically useful).",
}

# Well-known OS directories → meaning (context, not noise, but rarely the point)
OS_DIRS = [
    ("/Windows/System32", "Core Windows system binaries and drivers."),
    ("/Windows/SysWOW64", "32-bit system binaries on a 64-bit Windows."),
    ("/Windows/WinSxS", "Windows component store (side-by-side assemblies)."),
    ("/Windows/Prefetch", "Prefetch files recording program execution."),
    ("/Windows/Temp", "System temporary files."),
    ("/Windows", "Windows OS directory."),
    ("/Program Files (x86)", "Installed 32-bit applications."),
    ("/Program Files", "Installed applications."),
    ("/ProgramData", "Application data shared across users."),
    ("/$Recycle.Bin", "Recycle Bin — deleted files awaiting purge (high interest)."),
    ("/System Volume Information", "Restore points and volume shadow data."),
]

# User-area directories → meaning (this is usually where the evidence is)
USER_DIRS = [
    ("/Users/", "User profile area — documents, downloads, app data."),
    ("/Documents", "User documents."),
    ("/Downloads", "Downloaded files (common exfil/ingress point)."),
    ("/Desktop", "User desktop."),
    ("/AppData/Local/Temp", "Per-user temp folder (common staging location)."),
    ("/AppData", "Per-user application data."),
]

# File extensions → human category
EXT_MEANING = {
    ".exe": ("Executable program", NOTABLE),
    ".dll": ("Shared library", CONTEXT),
    ".sys": ("System driver", CONTEXT),
    ".7z": ("7-Zip archive (common for staging/exfil)", SIGNIFICANT),
    ".zip": ("Compressed archive", NOTABLE),
    ".rar": ("RAR archive (common for staging/exfil)", SIGNIFICANT),
    ".kdbx": ("KeePass password database (sensitive)", SIGNIFICANT),
    ".docx": ("Word document", NOTABLE),
    ".xlsx": ("Excel spreadsheet", NOTABLE),
    ".pdf": ("PDF document", NOTABLE),
    ".pst": ("Outlook mailbox", NOTABLE),
    ".lnk": ("Shortcut — records access to a target file", NOTABLE),
    ".log": ("Log file", CONTEXT),
    ".tmp": ("Temporary file", CONTEXT),
    ".bak": ("Backup file", NOTABLE),
}


def _basename(path):
    return os.path.basename(path.rstrip("/")) if path else ""


def _is_ntfs_system(path):
    """Match /$MFT, $MFT, /$BadClus:$Bad, /$Extend/$UsnJrnl etc."""
    p = (path or "").lstrip("/")
    if not p.startswith("$"):
        # also catch nested $Extend children
        if "/$" in ("/" + p):
            seg = "/" + p
        else:
            return None
    # try exact keys first
    for key in NTFS_SYSTEM:
        k = key.lstrip("/")
        if p == k or p.split(" (")[0] == k:
            return key
    # base token like "$MFT (something)"
    base = p.split("/")[0].split(":")[0].split(" ")[0]
    if base.startswith("$"):
        for key in NTFS_SYSTEM:
            if key.lstrip("/").split(":")[0] == base:
                return key
        return base  # unknown $-file, still system
    return None


def interpret_disk(ev):
    """
    ev is a parsed disk event dict (path, mode, size, mtime, crtime, …).
    Returns (category, relevance, severity, description, note).
    """
    path = ev.get("path", "") or ""
    name = _basename(path)
    is_dir = str(ev.get("mode", "")).startswith("d")
    is_deleted = "(deleted)" in path
    size = ev.get("size") or 0

    # 1. NTFS internal metadata — the noise
    sysk = _is_ntfs_system(path)
    if sysk:
        desc = NTFS_SYSTEM.get(sysk, "NTFS internal metadata structure.")
        note = ("Standard NTFS metadata present on every Windows volume — "
                "not evidence of user activity.")
        sev = 1
        # exceptions: these specific structures can hide data
        if "$BadClus:$Bad" in path and size and size > 10_000_000:
            sev = 4
            note = (f"$BadClus:$Bad is {size:,} bytes — abnormally large. Data can be "
                    "hidden in clusters falsely marked bad. Anti-forensic indicator.")
            return ("system_metadata", SIGNIFICANT, sev, desc, note)
        if "$UsnJrnl" in path:
            return ("system_metadata", CONTEXT, 1, desc,
                    "Change journal can corroborate file create/delete/rename activity.")
        return ("system_metadata", NOISE, sev, desc, note)

    # 2. deleted user content — always interesting
    if is_deleted and not path.lstrip("/").startswith("$"):
        ext = os.path.splitext(name)[1].lower()
        what, _ = EXT_MEANING.get(ext, ("File", NOTABLE))
        return ("user_file", SIGNIFICANT, 3,
                f"Deleted {what.lower()}: {name or path}",
                "File was deleted from a user-accessible location. Recoverable "
                "deleted files are frequently central to an investigation.")

    # 3. user-area files
    for frag, meaning in USER_DIRS:
        if frag.lower() in path.lower():
            ext = os.path.splitext(name)[1].lower()
            what, rel = EXT_MEANING.get(ext, ("File" if not is_dir else "Folder", NOTABLE))
            sev = 2 if rel in (NOTABLE,) else (3 if rel == SIGNIFICANT else 1)
            desc = f"{what}: {name}" if name else meaning
            note = meaning
            if rel == SIGNIFICANT:
                note = f"{meaning} {what} types are commonly involved in data theft."
            return ("user_file", rel, sev, desc, note)

    # 4. OS directories / files
    for frag, meaning in OS_DIRS:
        if frag.lower() in path.lower():
            rel = NOTABLE if "Recycle" in frag else CONTEXT
            sev = 2 if rel == NOTABLE else 1
            return ("os_file", rel, sev, (name or _basename(frag) or "OS file"), meaning)

    # 5. extension-based fallback for anything else
    ext = os.path.splitext(name)[1].lower()
    if ext in EXT_MEANING:
        what, rel = EXT_MEANING[ext]
        sev = 3 if rel == SIGNIFICANT else (2 if rel == NOTABLE else 1)
        return ("file", rel, sev, f"{what}: {name}",
                "Located outside the standard user profile.")

    # 6. generic file / folder
    kind = "Folder" if is_dir else "File"
    return ("file", CONTEXT, 1, f"{kind}: {name or path}",
            "Filesystem object with no specific forensic signature.")


# ── non-disk sources: describe by the event's own type ────────────────────────

EVENTLOG_MEANING = {
    "logon": ("Successful logon", NOTABLE, 2,
              "A user session started. After-hours or unusual logons matter."),
    "logon_failed": ("Failed logon attempt", NOTABLE, 2,
                     "Failed authentication — possible brute force or misuse."),
    "privilege": ("Special privileges assigned", NOTABLE, 2,
                  "Administrative privileges were granted to a session."),
    "process": ("Process created", NOTABLE, 1,
                "A program was launched (process-creation auditing)."),
    "service": ("New service installed", SIGNIFICANT, 3,
                "Service installation is a common persistence mechanism."),
    "install": ("Software installed", NOTABLE, 2,
                "An application was installed on the system."),
    "log_cleared": ("Security log cleared", SIGNIFICANT, 4,
                    "Clearing the event log is a classic anti-forensic action."),
}

REGISTRY_MEANING = {
    "usb": ("USB device history", SIGNIFICANT, 3,
            "Records a removable device that was connected — key for exfil cases."),
    "recent": ("RecentDocs entry", NOTABLE, 1,
               "Tracks recently opened files for the user."),
    "persistence": ("Run-key persistence", SIGNIFICANT, 3,
                    "Programs set to auto-start — a common persistence location."),
}

NETWORK_MEANING = {
    "dns": ("DNS query", NOTABLE, 1,
            "A domain name was resolved. Cloud-storage or odd domains matter."),
    "http": ("HTTP request", NOTABLE, 1,
             "A web request was made (cleartext HTTP)."),
}


def interpret_event(ev):
    """
    Top-level: route any unified event to an interpretation.
    Returns a dict the UI can use directly.
    """
    src = (ev.get("source") or "").lower()
    etype = ev.get("type", "")

    if src in ("disk", "downloads") or etype in ("file", "filesystem") or (ev.get("path", "").lstrip("/").startswith("$")):
        cat, rel, sev, desc, note = interpret_disk(ev)
    elif src == "eventlog":
        what, rel, sev, note = EVENTLOG_MEANING.get(
            etype, ("Windows event", CONTEXT, 1, "A recorded Windows event."))
        cat, desc = "eventlog", what
    elif src == "registry":
        what, rel, sev, note = REGISTRY_MEANING.get(
            etype, ("Registry artifact", CONTEXT, 1, "A registry value of interest."))
        cat, desc = "registry", what
    elif src == "network":
        what, rel, sev, note = NETWORK_MEANING.get(
            etype, ("Network event", NOTABLE, 1, "Observed network traffic."))
        cat, desc = "network", what
    elif src == "browser":
        cat, rel, sev = "browser", NOTABLE, 1
        desc = "Browser activity"
        note = "URL visit or download recorded in the browser database."
    elif src == "email":
        cat, rel, sev = "email", NOTABLE, (2 if "attachment" in (ev.get("label") or "").lower() else 1)
        desc = "Email message"
        note = "A mail item; attachments raise its relevance."
    else:
        cat, rel, sev, desc, note = ("event", CONTEXT, ev.get("sev", 1),
                                     ev.get("label", "Event"), "")

    return {"category": cat, "relevance": rel, "severity": sev,
            "description": desc, "note": note}


def generate_meaning(ev):
    """
    Produce the "WHAT IT MEANS" text for one event: a 1-2 sentence plain-English
    explanation of what the artifact is, what likely caused it, and whether it is
    something to be concerned about. This is deliberately SEPARATE from the EVENT
    column (which states *what happened* — the action + artifact).

    This is deliberately deterministic. It runs during bulk enrichment over
    every event in the timeline — thousands of synchronous LLM calls here would
    stall analysis for hours on CPU. The AI-written interpretation exists, but
    at the right layer: when the examiner selects an artifact, the evidence
    screen generates its "what it means" asynchronously through
    ai.surface_engine (validated against formats/what_it_means.md), with this
    deterministic note as the instant text and the fallback.

    `ev` must already carry the interpreter's `note`/`description` (i.e. call this
    after interpret_event has run, as enrich_events does).
    """
    note = (ev.get("note") or "").strip()
    if note:
        return note
    return "Interpretation pending — AI explanation will appear here."


def enrich_events(events):
    """
    Annotate a list of unified events in place with interpretation fields,
    and override the weak default label/sev with meaningful ones.
    Returns (events, stats) where stats summarises the relevance breakdown.
    """
    stats = {NOISE: 0, CONTEXT: 0, NOTABLE: 0, SIGNIFICANT: 0}

    # Detect the "every system file shares one timestamp" artifact: when many
    # events carry an identical timestamp it is almost always the volume-creation
    # time that fls stamps on NTFS metadata, NOT real activity at that instant.
    from collections import Counter
    ts_counts = Counter(str(e.get("timestamp", "")) for e in events)
    placeholder_ts = {ts for ts, n in ts_counts.items() if ts and n >= 10}

    for e in events:
        info = interpret_event(e)
        e["category"] = info["category"]
        e["relevance"] = info["relevance"]
        e["description"] = info["description"]
        e["note"] = info["note"]
        # upgrade severity if the interpreter found something the parser missed
        e["sev"] = max(e.get("sev", 1), info["severity"])
        # give it a readable label if it only had the generic one
        lab = e.get("label") or ""
        if (not lab) or lab.startswith("Filesystem —"):
            e["label"] = info["description"]
        # flag shared/placeholder timestamps so they aren't read as real timing
        if str(e.get("timestamp", "")) in placeholder_ts and e["relevance"] == NOISE:
            e["ts_placeholder"] = True
            extra = (" This timestamp is shared by many system files and reflects "
                     "volume creation, not activity at this moment.")
            e["note"] = (e["note"] + extra).strip()
        # WHAT IT MEANS — explanation distinct from the EVENT (what happened).
        # Placeholder for now; the AI model plugs in via generate_meaning().
        e["meaning"] = generate_meaning(e)
        stats[info["relevance"]] = stats.get(info["relevance"], 0) + 1
    return events, stats
