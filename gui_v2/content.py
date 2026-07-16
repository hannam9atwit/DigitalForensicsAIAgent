"""
gui_v2/content.py

The demo case (FA-2026-0142, "Suspected Data Exfiltration — Meridian Dynamics")
in the shape the screens render.

The copy here is lifted verbatim from the approved design prototype and is
treated as final content, not placeholder text. It serves two purposes:

  1. It is the fixture the UI is developed and demonstrated against.
  2. It documents the shape a real analysis has to produce. data_adapter.py
     fills the same keys from live pipeline output, so the screens never
     branch on "demo vs real".

Every finding answers the three questions the design is built around:
  what   — what happened, in plain English
  why    — why it matters, including confidence and the ATT&CK technique
            translated out of its bare code
  next   — what the examiner should do about it
"""

# ── Case metadata ─────────────────────────────────────────────────────────────

CASE_META = {
    "id": "FA-2026-0142",
    "title": "Suspected Data Exfiltration — Meridian Dynamics",
    "examiner": "M. Hanna",
    "examinerId": "EX-031",
    "agency": "Meridian Dynamics IR",
    "opened": "2026-06-05 09:18:02",
    "custodian": "M. Hanna",
    "riskScore": 87,
    "riskLabel": "HIGH",
    "riskCaption": "Driven by 2 critical findings on Jun 3.",
    "aiEngine": {
        "provider": "Ollama (local)",
        "model": "llama3.2:3b",
        "status": "online",
        "fallback": "Local → Cloud key (if set) → Rule-based",
    },
    "pipeline": {
        "lastRun": "2026-06-05 10:47:18",
        "duration": "4m 32s",
        "eventsParsed": 18402,
        "status": "complete",
    },
}

# The case overview's opening paragraph. (b) marks the terms the design renders
# at weight 500; (m) marks the filenames rendered in mono.
CASE_PARAGRAPH = [
    ("On the evening of ", None),
    ("Jun 3", "b"),
    (", after an unusual 18:42 sign-in, 31 Falcon project files were gathered "
     "into a hidden temp folder, archived as ", None),
    ("falcon_specs.7z", "m"),
    (" (482 MB), and copied to a SanDisk USB drive at 19:18. Within 15 minutes "
     "the local copies were deleted and the Windows security log was cleared. "
     "Planning searches from the day before bracket the sequence.", None),
]

NOISE_NOTE = ("1,214 routine system records are hidden as noise — nothing real "
              "is buried in them.")

TOTAL_EVENTS = 18402
HIDDEN_NOISE = 1214

# ── Phases ────────────────────────────────────────────────────────────────────

PHASES = [
    {"n": 1, "name": "Preparation", "when": "JUN 2 · 09:14 – 14:05",
     "desc": "The day before: research and tooling."},
    {"n": 2, "name": "Collection", "when": "JUN 3 · 18:42 – 19:10",
     "desc": "An unusual evening session; files gathered and archived."},
    {"n": 3, "name": "Exfiltration", "when": "JUN 3 · 19:15 – 19:21",
     "desc": "The archive leaves the machine on a USB drive."},
    {"n": 4, "name": "Cover-up", "when": "JUN 3 · 19:26 – 19:33",
     "desc": "Local copies deleted; the security log cleared."},
]

# ── Findings ──────────────────────────────────────────────────────────────────

FINDINGS = [
    {
        "id": "F-06", "sev": "MEDIUM", "conf": "Medium", "phase": 1,
        "title": "Search history shows planning",
        "short": "Searches about copying to USB and permanent deletion bracket the incident.",
        "what": "Searches including “how to copy large folders to usb faster” "
                "(Jun 2, 09:14) and “does emptying recycle bin permanently delete” "
                "(Jun 3, 19:31) bracket the incident.",
        "why": "Searches before the act suggest premeditation; searches after suggest "
               "awareness that traces needed removing. Confidence is medium — search "
               "intent alone is circumstantial. Technique TA0010: the searches indicate "
               "intent to move data out.",
        "next": ["Recover the browser-history gap after 19:33 from the vacuumed database"],
        "mitre": "TA0010", "ev": ["EV-02"],
    },
    {
        "id": "F-05", "sev": "HIGH", "conf": "Medium", "phase": 1,
        "title": "Archiving tool installed the day before",
        "short": "7-Zip was downloaded and installed Jun 2, then used to create the archive.",
        "what": "7-Zip 24.06 was downloaded from 7-zip.org and installed on Jun 2 at "
                "14:05 — the day before the incident — and was used to create "
                "falcon_specs.7z. The installer was deleted during cleanup.",
        "why": "Installing a compression tool right before using it to package company "
               "files suggests planning. Confidence is medium — the download and install "
               "are recorded, but the finding rests on timing. Technique T1560.001 "
               "(“Archive via utility”): packaging data before moving it.",
        "next": ["Check whether 7-Zip was sanctioned software for this user"],
        "mitre": "T1560.001", "ev": ["EV-03", "EV-01"],
    },
    {
        "id": "F-03", "sev": "HIGH", "conf": "High", "phase": 2,
        "title": "Sign-in far outside normal hours",
        "short": "Interactive logon at 18:42 — 4.8σ outside the user’s 90-day pattern.",
        "what": "The jcole account signed in at the keyboard (logon 4624, type 2) at "
                "18:42 on Jun 3 — far outside the user’s sign-in pattern from the "
                "previous 90 days.",
        "why": "The entire staging-and-transfer sequence happened during this unusual "
               "evening session. Confidence is high — the sign-in is recorded directly "
               "by Windows; the anomaly comes from a 90-day baseline. Technique T1078 "
               "(“Valid accounts”): using a legitimate login rather than breaking in.",
        "next": ["Corroborate with badge/door records for Jun 3 evening",
                 "Check for remote-access sessions in the same window"],
        "mitre": "T1078", "ev": ["EV-01"],
    },
    {
        "id": "F-04", "sev": "HIGH", "conf": "Medium", "phase": 2,
        "title": "Files gathered into a staging folder",
        "short": "31 project files (1.9 GB) copied into Temp\\_bk\\ minutes before archiving.",
        "what": "A temporary folder (Temp\\_bk\\) was created at 19:02 and 31 project "
                "files totalling 1.9 GB were copied into it over the following minutes.",
        "why": "Collecting files into one out-of-the-way folder is the classic "
               "preparation step before copying them out. Confidence is medium — copying "
               "alone can be innocent; the archive-and-transfer that followed makes it "
               "staging. Technique T1074.001 (“Local data staging”).",
        "next": ["Compare the 31 staged filenames against the Falcon sensitive-file inventory"],
        "mitre": "T1074.001", "ev": ["EV-01"],
    },
    {
        "id": "F-01", "sev": "CRITICAL", "conf": "High", "phase": 3,
        "title": "Project archive copied to a USB drive",
        "short": "falcon_specs.7z (482 MB) written to a SanDisk Cruzer at 19:18; "
                 "a password vault followed.",
        "what": "A 482 MB archive of Falcon project files was written to a SanDisk "
                "Cruzer USB drive at 19:18 on Jun 3 — under four minutes after the "
                "drive was plugged in. passwords_old.kdbx followed at 19:21.",
        "why": "This is the central event: staged company files physically left the "
               "machine. Confidence is high — three independent sources agree: the "
               "laptop filesystem (archive created 19:10), the registry (device serial "
               "4C53…8094 connected 19:15), and the USB image itself (archive present, "
               "written 19:18). Technique T1052.001: exfiltration over a physically "
               "connected drive.",
        "next": ["Acquire the physical SanDisk drive and verify its hash against the image",
                 "Confirm archive contents match the 31 staged files",
                 "Establish whether passwords_old.kdbx is a current vault"],
        "mitre": "T1052.001", "ev": ["EV-01", "EV-04", "EV-05"],
    },
    {
        "id": "F-02", "sev": "CRITICAL", "conf": "High", "phase": 4,
        "title": "Local copies deleted after the transfer",
        "short": "Archive, staging folder and installer deleted in a burst, 19:26–19:29.",
        "what": "Within three minutes of the USB write, the archive, the staging folder "
                "with all 31 files, and the 7-Zip installer were deleted in sequence — "
                "a burst 14× above this user’s normal deletion rate.",
        "why": "Deleting exactly the files involved, immediately after the transfer, "
               "points to deliberate concealment. Confidence is high — the MFT records "
               "each deletion, and the archive was later recovered intact from "
               "unallocated space. Technique T1070.004 (“Indicator removal: file "
               "deletion”).",
        "next": ["Hash the carved archive and compare it to the USB copy",
                 "Check Recycle Bin and shadow copies for remnants"],
        "mitre": "T1070.004", "ev": ["EV-01"],
    },
    {
        "id": "F-07", "sev": "HIGH", "conf": "High", "phase": 4,
        "title": "Windows security log cleared at 19:33",
        "short": "Event 1102 records the wipe itself, under the jcole account.",
        "what": "The Windows Security event log was cleared at 19:33 on Jun 3. The wipe "
                "records itself: Windows writes event 1102 (“the audit log was "
                "cleared”) as the first entry of the fresh log.",
        "why": "Clearing the security log destroys the record of sign-ins and file "
               "access around the transfer — one of the strongest signs of concealment. "
               "Confidence is high — event 1102 is direct evidence. Technique T1070.001: "
               "wiping the system’s own record of activity.",
        "next": ["Recover surviving events from log backups in the disk image",
                 "Check SIEM / event forwarding for copies of wiped entries"],
        "mitre": "T1070.001", "ev": ["EV-01"],
    },
]

# ── Evidence ──────────────────────────────────────────────────────────────────

EVIDENCE = [
    {
        "id": "EV-01", "name": "WS-0387_laptop.E01", "kind": "disk",
        "kindLabel": "Disk image", "size": "238.4 GB",
        "plain": "A complete, bit-for-bit copy of the employee’s laptop drive — "
                 "the main record of what happened on the machine.",
        "role": "It anchors most findings: the staging folder, the archive creation, "
                "the deletions, and the cleared log all come from this image.",
        "sha": "a3f1c9e07b6d44128f5a90cce21b7d3361e84f0a9bd2c5571e6643a8d90f12b7",
        "verified": True, "intake": "Jun 5 · 09:18",
    },
    {
        "id": "EV-02", "name": "History", "kind": "browser",
        "kindLabel": "Chrome history", "size": "12.7 MB",
        "plain": "What the user searched for and visited, with timestamps — 2,318 records.",
        "role": "It shows planning: searches about USB copying before the incident, "
                "and about permanent deletion after it.",
        "sha": "5e8b20c4d1aa97f3026e4b8d9c155af7e30d2b6a41c87e90f1d3a5b2c6e80417",
        "verified": True, "intake": "Jun 5 · 09:21",
    },
    {
        "id": "EV-03", "name": "Downloads", "kind": "browser",
        "kindLabel": "Chrome downloads", "size": "1.1 MB",
        "plain": "Files the user downloaded through Chrome — 87 records.",
        "role": "It records the 7-Zip installer download the day before the incident.",
        "sha": "9c44a7d2e6f08b315a92dc7e840b1f6235c8ad90e7b4612df30c5a18b9e2d764",
        "verified": True, "intake": "Jun 5 · 09:21",
    },
    {
        "id": "EV-04", "name": "SANDISK_CRUZER.dd", "kind": "disk",
        "kindLabel": "USB image", "size": "61.5 GB",
        "plain": "A complete copy of the USB drive the files were written to.",
        "role": "It independently confirms the transfer: the archive exists on the "
                "drive itself.",
        "sha": "1d7e3a92c5b8f04612ad96e3c70d5b2849f1e6a07c3d8b5410e92f6a7c4d0358",
        "verified": True, "intake": "Jun 5 · 09:44",
    },
    {
        "id": "EV-05", "name": "NTUSER.DAT", "kind": "registry",
        "kindLabel": "Registry hive", "size": "8.9 MB",
        "plain": "The user’s Windows settings — records USB devices, recent files "
                 "and program use.",
        "role": "It identifies the exact USB device (serial number) and when it was "
                "connected and removed.",
        "sha": "f08d6b41a2c97e5310bd84f6e2a90c7d5318be64a90f2c1d7e6354a8b0c91e25",
        "verified": False, "intake": "Jun 5 · 09:52",
    },
]

# ── Timeline ──────────────────────────────────────────────────────────────────
# rel: sig = significant (red left edge) · not = notable · ctx = context ·
#      noise = routine system record, hidden unless the noise toggle is on.

EVENTS = [
    {"ts": "Jun 2 09:14:31", "src": "Browser",
     "label": "Search: “how to copy large folders to usb faster”",
     "mean": "Research into moving large data to USB — a planning indicator",
     "rel": "sig", "fid": "F-06"},
    {"ts": "Jun 2 09:16:08", "src": "Browser",
     "label": "Visited dropbox.com (no login recorded)",
     "mean": "Possible alternative exfiltration channel considered",
     "rel": "not", "fid": "F-06"},
    {"ts": "Jun 2 14:03:12", "src": "Downloads",
     "label": "Downloaded 7z2406-x64.exe from 7-zip.org",
     "mean": "Compression tool acquired the day before the incident",
     "rel": "not", "fid": "F-05"},
    {"ts": "Jun 2 14:05:47", "src": "EventLog",
     "label": "7-Zip 24.06 installed (MsiInstaller 11707)",
     "mean": "The tool later used to package the project files",
     "rel": "not", "fid": "F-05"},
    {"ts": "Jun 3 18:42:09", "src": "EventLog",
     "label": "Interactive sign-in, jcole (logon 4624, type 2)",
     "mean": "At the keyboard, far outside normal hours — the session everything happened in",
     "rel": "sig", "fid": "F-03"},
    {"ts": "Jun 3 18:47:23", "src": "Disk",
     "label": "Mass read access begins: \\Projects\\Falcon\\ (34 files in 6 min)",
     "mean": "Project files being reviewed or selected",
     "rel": "not", "fid": "F-04"},
    {"ts": "Jun 3 19:00:41", "src": "Disk", "label": "$MFT record update",
     "mean": "Routine filesystem bookkeeping — exists on every Windows volume",
     "rel": "noise", "fid": None},
    {"ts": "Jun 3 19:02:11", "src": "Disk", "label": "Staging folder created: Temp\\_bk\\",
     "mean": "An out-of-the-way collection point — classic staging",
     "rel": "sig", "fid": "F-04"},
    {"ts": "Jun 3 19:04:55", "src": "Disk",
     "label": "31 project files copied into Temp\\_bk\\ (1.9 GB)",
     "mean": "The files that would later be archived and transferred",
     "rel": "sig", "fid": "F-04"},
    {"ts": "Jun 3 19:05:12", "src": "Disk", "label": "$Bitmap allocation update",
     "mean": "Routine filesystem bookkeeping", "rel": "noise", "fid": None},
    {"ts": "Jun 3 19:10:38", "src": "Disk",
     "label": "Archive created: falcon_specs.7z (482 MB)",
     "mean": "Staged files packaged for transport", "rel": "sig", "fid": "F-01"},
    {"ts": "Jun 3 19:11:03", "src": "Disk", "label": "$LogFile checkpoint",
     "mean": "Routine filesystem bookkeeping", "rel": "noise", "fid": None},
    {"ts": "Jun 3 19:15:02", "src": "Registry",
     "label": "USB connected: SanDisk Cruzer Glide (SN 4C53…8094)",
     "mean": "The destination device arrives — 4 minutes after archiving",
     "rel": "sig", "fid": "F-01"},
    {"ts": "Jun 3 19:18:47", "src": "USB",
     "label": "falcon_specs.7z written to removable volume E:\\",
     "mean": "The exfiltration itself: company data leaves the machine",
     "rel": "sig", "fid": "F-01"},
    {"ts": "Jun 3 19:20:00", "src": "EventLog",
     "label": "Scheduled task: SilentCleanup (routine)",
     "mean": "Standard Windows maintenance, unrelated to the user",
     "rel": "noise", "fid": None},
    {"ts": "Jun 3 19:21:13", "src": "USB", "label": "passwords_old.kdbx written to E:\\",
     "mean": "A credential vault follows the project data", "rel": "sig", "fid": "F-01"},
    {"ts": "Jun 3 19:24:30", "src": "Registry", "label": "USB device removal recorded",
     "mean": "Transfer complete; the drive is pulled", "rel": "ctx", "fid": None},
    {"ts": "Jun 3 19:26:05", "src": "Disk",
     "label": "falcon_specs.7z deleted (MFT entry unallocated)",
     "mean": "Cleanup begins 90 seconds after the drive is removed",
     "rel": "sig", "fid": "F-02"},
    {"ts": "Jun 3 19:27:41", "src": "Disk",
     "label": "Staging folder Temp\\_bk\\ deleted recursively (31 entries)",
     "mean": "The entire collection point erased at once", "rel": "sig", "fid": "F-02"},
    {"ts": "Jun 3 19:29:18", "src": "Disk", "label": "7z2406-x64.exe deleted from Downloads",
     "mean": "The tool itself removed — covering the preparation step",
     "rel": "not", "fid": "F-02"},
    {"ts": "Jun 3 19:31:52", "src": "Browser",
     "label": "Search: “does emptying recycle bin permanently delete”",
     "mean": "Checking whether the cleanup actually worked", "rel": "not", "fid": "F-06"},
    {"ts": "Jun 3 19:33:26", "src": "EventLog",
     "label": "Security log cleared (event 1102), account jcole",
     "mean": "The strongest concealment signal — the system’s own record wiped",
     "rel": "sig", "fid": "F-07"},
    {"ts": "Jun 4 11:38:40", "src": "Disk",
     "label": "Deleted archive carved intact from unallocated space",
     "mean": "Recovery during analysis — confirms exactly what was deleted",
     "rel": "not", "fid": "F-02"},
]

TL_SOURCES = ["All", "Disk", "Browser", "Downloads", "Registry", "EventLog", "USB"]

# ── Audit trail ───────────────────────────────────────────────────────────────
# kind: user (rust) · ok (green) · sys (grey)

AUDIT = [
    {"ts": "Jun 5 09:18:02", "who": "M. Hanna", "act": "CASE_CREATED",
     "detail": "Case FA-2026-0142 registered · intake form completed", "kind": "user"},
    {"ts": "Jun 5 09:18:02", "who": "M. Hanna", "act": "EVIDENCE_ADDED",
     "detail": "WS-0387_laptop.E01 · SHA-256 a3f1c9e0…f12b7 computed (read-only)",
     "kind": "user"},
    {"ts": "Jun 5 09:21:13", "who": "M. Hanna", "act": "EVIDENCE_ADDED",
     "detail": "History · SHA-256 5e8b20c4…0417 computed", "kind": "user"},
    {"ts": "Jun 5 09:21:13", "who": "M. Hanna", "act": "EVIDENCE_ADDED",
     "detail": "Downloads · SHA-256 9c44a7d2…d764 computed", "kind": "user"},
    {"ts": "Jun 5 09:44:37", "who": "M. Hanna", "act": "EVIDENCE_ADDED",
     "detail": "SANDISK_CRUZER.dd · SHA-256 1d7e3a92…0358 computed", "kind": "user"},
    {"ts": "Jun 5 09:52:20", "who": "M. Hanna", "act": "EVIDENCE_ADDED",
     "detail": "NTUSER.DAT · hive dirty, parsed in recovery mode", "kind": "user"},
    {"ts": "Jun 5 10:42:51", "who": "system", "act": "HASH_VERIFIED",
     "detail": "4/5 artifacts re-verified OK (EV-05 pending)", "kind": "ok"},
    {"ts": "Jun 5 10:43:08", "who": "system", "act": "ANALYSIS_STARTED",
     "detail": "Full pipeline · 5 artifacts queued", "kind": "sys"},
    {"ts": "Jun 5 10:47:18", "who": "system", "act": "ANALYSIS_COMPLETE",
     "detail": "18,402 events · 7 findings · risk 87/100", "kind": "ok"},
    {"ts": "Jun 5 10:47:20", "who": "system", "act": "NARRATIVE_GENERATED",
     "detail": "Draft narrative written by local model (llama3.2)", "kind": "sys"},
]

# ── Report ────────────────────────────────────────────────────────────────────

REPORT_ORDER = ["F-01", "F-02", "F-07", "F-03", "F-04", "F-05", "F-06"]

# F-06 is excluded by default — it is the weakest finding, and the design uses
# it to show that the examiner curates what goes in the report.
REPORT_DEFAULT_INCLUDE = {
    "F-01": True, "F-02": True, "F-07": True, "F-03": True,
    "F-04": True, "F-05": True, "F-06": False,
}

REPORT_TITLE = "Report of Digital Forensic Examination"
REPORT_BYLINE = ("Examiner M. Hanna (EX-031) · Generated 2026-06-05 10:47 · "
                 "Drafted by the local model, reviewed by the examiner")
REPORT_SUMMARY = (
    "The examined evidence is consistent with a deliberate, premeditated "
    "exfiltration of proprietary project data from workstation WS-0387 by the "
    "user account jcole. A 482 MB archive of staged Falcon project files was "
    "transferred to a SanDisk Cruzer USB device on 2026-06-03 at 19:18, followed "
    "by coordinated deletion of the local copies and clearing of the Windows "
    "security log at 19:33.")
REPORT_FOOTER = (
    "The exported PDF embeds the SHA-256 of all five artifacts and the full "
    "audit trail.\nEvidence was mounted read-only throughout the examination.")

# ── Ask the AI ────────────────────────────────────────────────────────────────

SUGGESTED = [
    "Why do you think the archive was exfiltrated?",
    "What happened between 19:15 and 19:35?",
    "Which findings are the weakest?",
]

# Canned answers for the suggested prompts. The design uses these as the quality
# bar for real model output: multi-paragraph, cites sources, states uncertainty
# explicitly rather than hiding it.
ANSWERS = [
    {
        "paras": [
            "Three independent artifacts tell the same story, which is why I treat "
            "the exfiltration as well-supported rather than assumed.",
            "The laptop’s filesystem shows falcon_specs.7z being created from 31 "
            "staged project files at 19:10. The registry then records a SanDisk Cruzer "
            "(serial 4C53…8094) connecting at 19:15. The USB drive image itself contains "
            "that same archive, written at 19:18. No single source would be conclusive — "
            "together, and in this order, they form one continuous sequence.",
            "The cleanup that followed (deletions at 19:26–19:29, security log cleared "
            "at 19:33) is what shifts this from “files were copied” to "
            "“files were copied and concealed.”",
        ],
        "uncertain": "I can’t establish who was physically at the keyboard — the "
                     "sign-in used jcole’s valid credentials. Badge records or "
                     "camera footage would resolve that.",
        "chips": [("EV-01 · Disk image", "EV-01"), ("EV-05 · Registry", "EV-05"),
                  ("EV-04 · USB image", "EV-04")],
    },
    {
        "paras": [
            "A minute-by-minute reconstruction of that 20-minute window:",
            "19:15:02 — SanDisk Cruzer USB drive connects (registry). 19:18:47 — "
            "falcon_specs.7z (482 MB) is written to the drive. 19:21:13 — "
            "passwords_old.kdbx is written to the drive. 19:24:30 — the drive is "
            "removed. 19:26:05 — the local archive is deleted. 19:27:41 — the staging "
            "folder and all 31 files are deleted. 19:29:18 — the 7-Zip installer is "
            "deleted. 19:31:52 — search: “does emptying recycle bin permanently "
            "delete”. 19:33:26 — the Windows security log is cleared.",
            "The rhythm matters: transfer, then removal, then cleanup, then "
            "verification of the cleanup — each step within minutes of the last.",
        ],
        "uncertain": "Timestamps come from three different clocks (NTFS, registry, "
                     "browser). I’ve aligned them, but sub-minute ordering between "
                     "sources carries some tolerance.",
        "chips": [("Timeline 19:15–19:35", "TL"), ("EV-01 · Disk image", "EV-01")],
    },
    {
        "paras": [
            "The two findings I’d treat most carefully are the staging folder "
            "(F-04) and the search history (F-06) — both are marked medium confidence.",
            "F-04: copying files to a temp folder is only “staging” because of "
            "what followed; on its own it could be a backup. F-06: searches show intent "
            "but not action — people search things they never do. Neither would stand "
            "alone; they matter as context around the high-confidence core (the USB "
            "transfer, the deletions, the cleared log).",
        ],
        "uncertain": "If you exclude F-04 and F-06 entirely, the case’s core "
                     "sequence still holds — I’d recommend framing them as "
                     "corroborating context in the report.",
        "chips": [("F-04 · Staging", "F-04"), ("F-06 · Searches", "F-06")],
    },
]

FALLBACK_ANSWER = {
    "paras": [
        "Working from this case’s evidence: the sequence on Jun 3 — staging at "
        "19:02, archiving at 19:10, USB transfer at 19:18, cleanup from 19:26 — is the "
        "core of what I can speak to. Could you point me at a time window, artifact, or "
        "finding you want unpacked?",
    ],
    "uncertain": "I only reason over the five artifacts in this case. Anything outside "
                 "them (other machines, network logs, personnel context) is beyond what "
                 "I can see.",
    "chips": [("Timeline", "TL")],
}

# ── Sealed viewer fixtures ────────────────────────────────────────────────────

TIERS = [
    ("Raw preview", "Bytes, text and metadata exactly as stored. The safest look."),
    ("Rendered view", "Parsed into readable records. Remote content always blocked."),
    ("Browse the files", "Walk the disk image’s folders. Deleted items are marked."),
]

SEALED_NOTE = ("<b>Sealed viewer.</b> Evidence is parsed and drawn by the app — never "
               "opened by its own program, at any level.")

HEX_LINES = [
    "00000000  37 7A BC AF 27 1C 00 04  5B 38 E9 A2 D0 8A 01 00",
    "00000010  00 00 00 00 23 00 00 00  00 00 00 00 8E F4 6C 91",
    "00000020  E4 A7 01 09 80 AB 00 07  0B 01 00 01 21 07 00 0C",
    "00000030  8F 8A 4A 06 F5 BD 39 C0  63 81 07 F7 4D 79 62 1E",
    "00000040  5D 00 3A 01 12 89 D2 6B  22 5E B1 90 41 CC 0F 03",
    "00000050  01 84 3F 96 7A DD 08 30  16 5A 4E FF 2C 71 90 A5",
    "00000060  4B 0D E2 33 87 C4 19 6E  A0 55 3C 12 D8 91 47 BB",
    "…",
    "SIGNATURE  37 7A BC AF 27 1C — valid 7-Zip archive header",
]

# Tier 2 · browser. tag warn=True renders in critical red, False in accent.
HISTORY_ROWS = [
    ("Jun 2 · 09:14:31", "Search: “how to copy large folders to usb faster”",
     "PLANNING", True),
    ("Jun 2 · 09:16:08", "Visited dropbox.com (no login recorded)", "NOTABLE", False),
    ("Jun 2 · 14:03:12", "Downloaded 7z2406-x64.exe from 7-zip.org", "NOTABLE", False),
    ("Jun 3 · 19:31:52", "Search: “does emptying recycle bin permanently delete”",
     "COVER-UP", True),
    ("Jun 3 · 19:33:26", "History records end — gap until 23:59", "GAP", True),
]
HISTORY_CAPTION = ("Parsed from SQLite — remote content, favicons and scripts are "
                   "never fetched.")

# Tier 2 · registry. (text, indent, highlighted)
REGISTRY_ROWS = [
    ("▸ HKCU\\Software", 0, False),
    ("▾ HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USBSTOR", 0, False),
    ("▾ Disk&Ven_SanDisk&Prod_Cruzer_Glide", 1, False),
    ("● 4C530001180094  ← connected Jun 3 19:15:02", 2, True),
    ("FriendlyName: SanDisk Cruzer Glide USB Device", 3, False),
    ("LastArrival: 2026-06-03 19:15:02", 3, True),
    ("LastRemoval: 2026-06-03 19:24:30", 3, True),
    ("▸ RecentDocs (41 entries)", 0, False),
    ("▸ UserAssist (program-use counts)", 0, False),
]

# Tier 3 · filesystem. (text, indent, deleted, tag)
TREE_ROWS = [
    ("▾ C:\\", 0, False, ""),
    ("▸ Projects\\Falcon\\  (34 files)", 1, False, ""),
    ("▾ Users\\jcole\\", 1, False, ""),
    ("▸ Downloads\\", 2, False, ""),
    ("▾ AppData\\Local\\Temp\\", 2, False, ""),
    ("▾ _bk\\", 3, True, "DELETED · RECOVERED"),
    ("falcon_specs.7z  482 MB", 4, True, "CARVED INTACT"),
    ("Falcon_Avionics_ICD.pdf", 4, True, "DELETED"),
    ("Falcon_Prop_Deck_v12.pptx", 4, True, "DELETED"),
    ("+ 28 more deleted entries…", 4, True, ""),
]

ARCHIVE_ROWS = [
    ("Falcon_Avionics_ICD.pdf", "48.2 MB"),
    ("Falcon_Prop_Deck_v12.pptx", "112.4 MB"),
    ("guidance_calib_dataset.csv", "203.1 MB"),
    ("Falcon_BOM_2026.xlsx", "2.4 MB"),
    ("test_flight_logs/ (14 files)", "96.7 MB"),
    ("+ 12 more…", ""),
]

ARCHIVE_NOTICE = ("The deleted archive was carved intact from unallocated space. Its "
                  "contents are listed below — read from the archive index, never "
                  "extracted or executed.")

# ── Launch / intake / analyzing ───────────────────────────────────────────────

RECENT_CASES = [
    {"id": "FA-2026-0142", "title": "Suspected Data Exfiltration — Meridian Dynamics",
     "meta": "Analyzed Jun 5 · 7 findings · 5 artifacts", "risk": "RISK 87", "hot": True},
    {"id": "FA-2026-0117", "title": "Phishing triage — Hollis & Co.",
     "meta": "Closed May 22 · 3 findings · 2 artifacts", "risk": "RISK 41", "hot": False},
    {"id": "FA-2026-0098", "title": "HR device review — R. Patel",
     "meta": "Closed May 02 · no findings · 1 artifact", "risk": "RISK 6", "hot": False},
]

SUPPORTED_FORMATS = ("Disk images (E01 · dd · raw) · Windows event logs (EVTX) · "
                     "Registry hives · Chrome artifacts · PCAP · Email (mbox/eml) · "
                     "Prefetch")

ANALYSIS_STAGES = [
    ("Hash & register evidence", "SHA-256 × 5"),
    ("Parse artifacts", "SleuthKit · SQLite · hive"),
    ("Build unified timeline", "18,402 events"),
    ("Run rules & anomaly detection", "7 findings"),
    ("Draft narrative (local model)", "llama3.2 · offline"),
]

ANALYSIS_LOGS = [
    "Hashing WS-0387_laptop.E01…",
    "Parsing NTFS · recovering deleted entries…",
    "Correlating 5 sources into one sequence…",
    "Applying DFIR rules · baselining behaviour…",
    "Drafting narrative on this machine…",
    "Done.",
]

INTAKE_FILES = [
    ("WS-0387_laptop.E01", "Disk image · EnCase", "238.4 GB"),
    ("History", "Chrome history · SQLite", "12.7 MB"),
    ("SANDISK_CRUZER.dd", "USB image · raw", "61.5 GB"),
    ("NTUSER.DAT", "Registry hive", "8.9 MB"),
]

# ── Sidebar ───────────────────────────────────────────────────────────────────

STEPS = [
    ("case", "Case", "Risk 87 · high"),
    ("evidence", "Evidence", "5 artifacts · 4 verified"),
    ("timeline", "Timeline", "18,402 events"),
    ("findings", "Findings", "7 findings · 2 critical"),
    ("report", "Report", "Draft ready"),
]

EXTRAS = [
    ("chat", "Ask the AI"),
    ("audit", "Audit trail"),
    ("settings", "Settings"),
]

# ── Rail copy for screens without a per-item selection ────────────────────────

RAIL_STATIC = {
    "case": ("Case overview", [
        ("WHAT IS THIS?", "The case at a glance: risk, what was found, "
                          "chain-of-custody status, and where to start."),
        ("WHAT SHOULD I DO FIRST?", "Follow the “Start here” list — it orders "
                                    "the three highest-value moves for this case."),
    ], []),
    "timeline": ("The timeline — in plain terms", [
        ("WHAT IS THIS?", "Every event from all five artifacts, merged into one "
                          "sequence on one clock."),
        ("WHY AM I SEEING IT?", "Individual artifacts only show fragments. The merged "
                                "view is where the story appears — staging on the disk, "
                                "the USB in the registry, the transfer on the drive image."),
    ], ["Select any row to see what it means and which finding it supports",
        "Red-edged rows are the significant ones — start there"]),
    "report": ("The report — in plain terms", [
        ("WHAT IS THIS?", "A court-ready PDF: the AI-drafted narrative, the findings you "
                          "include, your remarks, and the full chain-of-custody record."),
        ("WHY DOES IT MATTER?", "This document may be read by lawyers, HR, or a court. "
                                "Everything in it traces back to evidence, and generating "
                                "it is logged in the audit trail."),
    ], ["Read the AI draft critically — you sign the report, not the model",
        "Exclude findings you consider unsupported",
        "Add remarks for anything the reader needs context on"]),
    "chat": ("The assistant — in plain terms", [
        ("WHAT IS THIS?", "A local model that has read this case’s timeline, "
                          "findings and evidence metadata — and nothing else."),
        ("CAN I TRUST IT?", "Treat it like a junior analyst: useful for orientation, "
                            "never a substitute for the evidence. Every answer cites "
                            "sources — click them and check. It flags its own uncertainty "
                            "rather than hiding it."),
        ("IS THIS PRIVATE?", "Yes. The model runs on this machine. No question or "
                             "evidence leaves it unless you set a cloud key in Settings — "
                             "and even then, evidence files never do."),
    ], []),
    "audit": ("The audit trail — in plain terms", [
        ("WHAT IS THIS?", "An append-only log of every action taken on this case: "
                          "intake, hashing, analysis, exports, even AI questions."),
        ("WHY DOES IT MATTER?", "If this case is ever challenged, this log is how you "
                                "show the evidence was never altered and every step is "
                                "accounted for. That is why nothing here can be edited."),
    ], []),
    "settings": ("Settings — in plain terms", [
        ("WHAT IS THIS?", "Your identity (it appears on reports and audit entries) and "
                          "the AI engine configuration."),
        ("WHAT STAYS PRIVATE?", "Everything, by default. The app is built to run with no "
                                "network at all. A cloud API key is optional, held in "
                                "memory only, and never sees the evidence files themselves."),
    ], []),
}

RAIL_FOOTER = ("This panel always answers: what is this, why am I seeing it, and what "
               "should I do. Select anything to update it.")

EVIDENCE_SAFE_BLOCK = (
    "IS IT SAFE TO LOOK?",
    "Yes. Every level of the viewer reads a sealed copy. Nothing is executed, and remote "
    "content is blocked. The SHA-256 recorded on intake proves the copy is unchanged.")

EVIDENCE_STEPS = ["Check the integrity stamp before relying on this artifact",
                  "Use the raw preview if you need to cite exact bytes"]

START_HERE = [
    ("01", "Read F-01 — the USB transfer",
     "The central finding, corroborated by 3 sources", ("findings", "F-01")),
    ("02", "Walk the 19:15–19:35 window",
     "Transfer and cover-up, minute by minute", ("timeline", "Jun 3 19:18:47")),
    ("03", "Re-verify NTUSER.DAT",
     "The one artifact whose hash check is pending", ("evidence", "EV-05")),
]

PIPELINE_ROWS = [
    ("Last run", "Jun 5 · 10:47"),
    ("Duration", "4m 32s"),
    ("Events parsed", "18,402"),
    ("Engine", "Local · llama3.2"),
]


def demo_case() -> dict:
    """The demo case as the screens' case dict."""
    return {
        "loaded": True,
        "demo": True,
        "caseMeta": dict(CASE_META),
        "evidence": [dict(e) for e in EVIDENCE],
        "events": [dict(e) for e in EVENTS],
        "findings": [dict(f) for f in FINDINGS],
        "phases": [dict(p) for p in PHASES],
        "audit": [dict(a) for a in AUDIT],
        "paragraph": CASE_PARAGRAPH,
        "report": {
            "title": REPORT_TITLE,
            "byline": REPORT_BYLINE,
            "summary": REPORT_SUMMARY,
            "footer": REPORT_FOOTER,
            "order": list(REPORT_ORDER),
            "include": dict(REPORT_DEFAULT_INCLUDE),
        },
    }
