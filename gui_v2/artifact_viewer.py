"""
gui_v2/artifact_viewer.py

The read-only backend for the evidence viewer. It reads the ACTUAL selected
artifact from disk and produces real content for each viewer tier:

    raw_preview(path)      -> real hex + ASCII of the first bytes, real
                              signature, real size
    rendered_records(...)  -> real parsed records routed by artifact kind
    file_tree(path)        -> real filesystem listing from a disk image (fls)

The safety model is parse-and-draw, exactly as the UI promises: files are
opened read-only, nothing is executed, and no artifact is handed to its native
application. There are no containers because none are needed for this model,
only disciplined read-only parsing.

Every function fails soft and honest: on any error it returns a structure the
UI can render as a plain message ("couldn't read this file: ...") rather than
crashing or, worse, showing placeholder content.
"""

import os
import struct

_HEX_BYTES_DEFAULT = 4096
_HEX_WIDTH = 16

# (magic bytes, offset, label). First match wins; order longest/most-specific
# first where prefixes overlap.
_SIGNATURES = [
    (b"\xD4\xC3\xB2\xA1", 0, "pcap capture (little-endian)"),
    (b"\xA1\xB2\xC3\xD4", 0, "pcap capture (big-endian)"),
    (b"\x0A\x0D\x0D\x0A", 0, "pcapng capture"),
    (b"7z\xBC\xAF\x27\x1C", 0, "7-Zip archive"),
    (b"PK\x03\x04", 0, "ZIP / Office / JAR archive"),
    (b"Rar!\x1A\x07", 0, "RAR archive"),
    (b"ElfFile\x00", 0, "Windows Event Log (.evtx)"),
    (b"regf", 0, "Windows registry hive"),
    (b"SQLite format 3\x00", 0, "SQLite database"),
    (b"EVF\x09\x0D\x0A\xFF\x00", 0, "EnCase evidence file (E01)"),
    (b"\x89PNG\r\n\x1A\n", 0, "PNG image"),
    (b"\xFF\xD8\xFF", 0, "JPEG image"),
    (b"%PDF-", 0, "PDF document"),
    (b"MZ", 0, "Windows executable (PE)"),
    (b"\x7FELF", 0, "ELF executable"),
    (b"From ", 0, "mbox mail archive"),
]

# Which artifact kinds have a real rendered view, and the human name shown
# when one does not.
_KIND_LABELS = {
    "network": "network capture",
    "eventlog": "Windows event log",
    "registry": "registry hive",
    "browser": "browser database",
    "email": "mail archive",
    "disk": "disk image",
    "prefetch": "prefetch",
}


def raw_preview(path: str, max_bytes: int = _HEX_BYTES_DEFAULT) -> dict:
    """Real hex + ASCII dump and metadata for the first bytes of the file."""
    if not path or not os.path.isfile(path):
        return {"error": f"file not found on disk: {path or '(no path)'}"}

    try:
        size = os.path.getsize(path)
        with open(path, "rb") as artifact:
            data = artifact.read(max_bytes)
    except OSError as error:
        return {"error": f"couldn't read this file: {error}"}

    return {
        "error": "",
        "size_bytes": size,
        "shown_bytes": len(data),
        "signature": _detect_signature(data),
        "hex_lines": _hex_lines(data),
    }


def _detect_signature(data: bytes) -> str:
    for magic, offset, label in _SIGNATURES:
        if data[offset:offset + len(magic)] == magic:
            return label
    return "no recognized signature (unknown or headerless format)"


def _hex_lines(data: bytes) -> list:
    """List of (offset, hex, ascii) tuples, one per 16-byte row."""
    lines = []
    for start in range(0, len(data), _HEX_WIDTH):
        chunk = data[start:start + _HEX_WIDTH]
        hex_part = " ".join(f"{byte:02X}" for byte in chunk)
        hex_part = hex_part.ljust(_HEX_WIDTH * 3 - 1)
        ascii_part = "".join(
            chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append((f"{start:08X}", hex_part, ascii_part))
    return lines


def rendered_records(path: str, kind: str, log=lambda _m: None) -> dict:
    """Real parsed records for the artifact, routed by kind.

    Returns {"columns", "rows", "note", "error", "supported"}. When no parser
    exists for the kind, supported is False and note explains it honestly, so
    the UI shows the truth instead of fabricated rows.
    """
    if not path or not os.path.isfile(path):
        return _unsupported(f"file not found on disk: {path or '(no path)'}",
                            supported=True, error=True)

    router = {
        "network": _render_network,
        "browser": _render_browser,
        "registry": _render_registry,
        "eventlog": _render_eventlog,
        "email": _render_email,
    }
    handler = router.get(kind)
    if handler is None:
        label = _KIND_LABELS.get(kind, kind or "this type")
        if kind == "disk":
            return _unsupported(
                "Disk images are explored in the Browse the files tier, which "
                "lists the real filesystem from the image.")
        return _unsupported(f"No rendered view for {label} yet. Use Raw "
                            f"preview to inspect the bytes directly.")

    try:
        return handler(path, log)
    except Exception as error:  # a bad file must not crash the viewer
        return _unsupported(f"couldn't parse this artifact: {error}",
                            supported=True, error=True)


def _unsupported(note: str, supported: bool = False, error: bool = False) -> dict:
    return {"columns": [], "rows": [], "note": note,
            "error": note if error else "", "supported": supported}


# The rendered view only shows the first 500 rows, so it reads only a few
# thousand packets. A pure-Python decode holds the GIL; reading the pipeline's
# full 50k here would freeze the UI even though the parse is off-thread. This is
# enough to fill the table on any real capture and returns in well under a
# second. The full analysis pass keeps the larger default cap.
_VIEW_PACKET_CAP = 2000


def _render_network(path, log):
    from modules.network.pcap_parser import PCAPParser
    result = PCAPParser().parse(path, max_packets=_VIEW_PACKET_CAP)
    if result.get("error") and not result.get("events"):
        return _unsupported(result["error"], supported=True, error=True)

    rows = []
    for event in result.get("events", [])[:500]:
        rows.append([
            _fmt_time(event.get("timestamp")),
            event.get("src_ip", ""),
            event.get("dst_ip", ""),
            event.get("proto", ""),
            _port_pair(event.get("sport"), event.get("dport")),
        ])

    packets = result.get("packets", 0)
    if result.get("truncated"):
        note = (f"First {packets:,} packets read — this capture is large, so the "
                f"preview is capped for responsiveness (the full analysis reads "
                f"more)")
    else:
        note = f"{packets:,} packets read"
    if len(rows) == 500:
        note += "; showing first 500"
    return {"columns": ["Time", "Source", "Destination", "Proto", "Ports"],
            "rows": rows, "note": note, "error": "", "supported": True}


def _render_browser(path, log):
    from modules.browser.history_parser import HistoryParser
    parsed = HistoryParser().parse(path)
    rows = []
    for visit in parsed.get("visits", [])[:500]:
        rows.append([
            _fmt_time(visit.get("visit_time")),
            (visit.get("title") or "")[:60],
            (visit.get("url") or "")[:80],
        ])
    if not rows:
        return _unsupported("No history rows found in this database.",
                            supported=True)
    return {"columns": ["Time", "Title", "URL"], "rows": rows,
            "note": f"{len(rows)} visits", "error": "", "supported": True}


def _render_registry(path, log):
    try:
        from modules.windows.registry_parser import RegistryParser
    except ImportError:
        return _unsupported(
            "Registry rendering needs the 'regipy' package, which isn't "
            "installed. Raw preview still works.", supported=True)
    parsed = RegistryParser().parse(path)
    rows = [[key.get("path", ""), key.get("value", "")]
            for key in parsed.get("keys", [])[:500]]
    return {"columns": ["Key", "Value"], "rows": rows,
            "note": f"{len(rows)} keys", "error": "", "supported": True}


def _render_eventlog(path, log):
    try:
        from modules.windows.evtx_parser import EventLogParser
    except ImportError:
        return _unsupported(
            "Event log rendering needs the 'python-evtx' package, which isn't "
            "installed. Raw preview still works.", supported=True)
    parsed = EventLogParser().parse(path)
    rows = []
    for record in parsed.get("events", [])[:500]:
        rows.append([
            _fmt_time(record.get("timestamp")),
            str(record.get("event_id", "")),
            (record.get("description") or "")[:80],
        ])
    return {"columns": ["Time", "Event ID", "Description"], "rows": rows,
            "note": f"{len(rows)} records", "error": "", "supported": True}


def _render_email(path, log):
    try:
        from modules.email_fx.mbox_parser import EmailParser
    except ImportError:
        return _unsupported(
            "No email parser is installed. Raw preview still works.",
            supported=True)
    parsed = EmailParser().parse(path)
    rows = []
    for message in parsed.get("messages", [])[:500]:
        rows.append([
            _fmt_time(message.get("date")),
            (message.get("from") or "")[:40],
            (message.get("subject") or "")[:70],
        ])
    return {"columns": ["Date", "From", "Subject"], "rows": rows,
            "note": f"{len(rows)} messages", "error": "", "supported": True}


def file_tree(path: str, kind: str, log=lambda _m: None) -> dict:
    """Real filesystem listing from a disk image via SleuthKit fls.

    Returns {"entries", "note", "error", "supported"}. Only disk images are
    walkable; other kinds return supported=False with the reason.
    """
    if kind != "disk":
        return {"entries": [], "supported": False,
                "note": "Browsing applies to disk images only. This artifact "
                        "is inspected through Raw preview and Rendered view.",
                "error": ""}
    if not path or not os.path.isfile(path):
        return {"entries": [], "supported": True,
                "note": "", "error": f"disk image not found: {path}"}

    try:
        from core.tool_runner import ToolRunner
        runner = ToolRunner()
        entries, error = _run_fls(runner, path)
    except Exception as error:
        return {"entries": [], "supported": True, "note": "",
                "error": f"couldn't read the image's filesystem: {error}"}

    if error:
        return {"entries": [], "supported": True, "note": "", "error": error}

    deleted = sum(1 for entry in entries if entry["deleted"])
    note = f"{len(entries)} entries"
    if deleted:
        note += f" · {deleted} deleted/recovered"
    if len(entries) == _FLS_ENTRY_CAP:
        note += f" (showing first {_FLS_ENTRY_CAP})"
    return {"entries": entries, "supported": True, "note": note, "error": ""}


def _run_fls(runner, path):
    """Run fls, handling both single-volume images and full disk images.

    A full disk image has a partition table, so fls must be told the
    filesystem's SECTOR offset with -o (fls -o counts sectors, not bytes); run
    against the whole image it fails with "Cannot determine file system type".

    Attempts, in order:
      1. fls directly — works for single-volume/partition images.
      2. fls -o <offset> using core.partition_detector.detect_ntfs_offset —
         the exact partition-offset path the analysis pipeline used to read this
         image (it returns the NTFS start in sectors, e.g. 65664), so an image
         that analysed successfully browses successfully too.
      3. fls -o <sector> at every filesystem partition mmls reports — covers
         non-NTFS filesystems detect_ntfs_offset skips.

    Returns (entries, error_message). On failure the message carries the
    complete stderr from every attempt, never a fragment.
    """
    from core.partition_detector import detect_ntfs_offset

    attempts = []  # (label, result) — kept so the error shows full stderr

    # Attempt 1: image is a single filesystem (no partition table).
    direct = runner.run_tsk(["fls", "-r", "-p", path], image_path=path)
    if direct.get("returncode") == 0 and direct.get("stdout", "").strip():
        return _parse_fls(direct["stdout"]), ""
    attempts.append(("fls (no offset)", direct))

    # Attempt 2: the pipeline's partition-offset path — detect the NTFS start in
    # sectors and pass it straight to fls -o (NOT multiplied to bytes).
    detected = 0
    try:
        detected = detect_ntfs_offset(path)
    except Exception as error:  # detection must never crash the viewer
        attempts.append(("detect_ntfs_offset",
                         {"stderr": str(error), "returncode": -1}))
    if detected:
        at_offset = runner.run_tsk(
            ["fls", "-r", "-p", "-o", str(detected), path], image_path=path)
        if at_offset.get("returncode") == 0 and at_offset.get("stdout", "").strip():
            return _parse_fls(at_offset["stdout"]), ""
        attempts.append((f"fls -o {detected}", at_offset))

    # Attempt 3: enumerate every filesystem partition with mmls and try each
    # (sector offsets). Skips the offset already tried in attempt 2.
    mmls = runner.run_tsk(["mmls", path], image_path=path)
    if mmls.get("returncode") == 0:
        for sector in _parse_mmls_offsets(mmls.get("stdout", "")):
            if sector == detected:
                continue
            part = runner.run_tsk(
                ["fls", "-r", "-p", "-o", str(sector), path], image_path=path)
            if part.get("returncode") == 0 and part.get("stdout", "").strip():
                return _parse_fls(part["stdout"]), ""
            attempts.append((f"fls -o {sector}", part))
    else:
        attempts.append(("mmls", mmls))

    return [], _fls_error(attempts)


def _fls_error(attempts):
    """Compose a browse-failure message that preserves the COMPLETE stderr from
    every attempt, so it is never cut off mid-sentence."""
    details = []
    combined = ""
    for label, result in attempts:
        stderr = (result.get("stderr") or "").strip()
        if stderr:
            details.append(f"{label}: {stderr}")
            combined += " " + stderr.lower()

    body = (" | ".join(details) if details
            else "no filesystem was found and no error text was returned")

    hint = ""
    if "not found" in combined or "tool not found" in combined:
        hint = (" SleuthKit binaries are needed to browse disk images; they "
                "ship with the installer in bin/sleuthkit.")
    elif "cannot determine" in combined or not details:
        hint = (" The image may be encrypted, use an unsupported filesystem, or "
                "be a container format this build doesn't mount.")
    return f"fls could not read this image. {body}.{hint}"


def _parse_mmls_offsets(output):
    """Filesystem partition start SECTORS from mmls output.

    fls -o expects a sector offset, so these are passed through unchanged — the
    earlier code multiplied by 512 to make a byte offset, which fls then read as
    a sector number far past the end of the image, so every offset attempt
    failed even when the partition was found.
    """
    offsets = []
    for line in output.splitlines():
        parts = line.split()
        # mmls rows: NN:  meta/---  <start>  <end>  <length>  <description>
        if len(parts) >= 6 and parts[0].rstrip(":").isdigit():
            descriptor = " ".join(parts[5:]).lower()
            if any(skip in descriptor for skip in
                   ("unallocated", "meta", "primary table", "extended")):
                continue
            try:
                offsets.append(int(parts[2]))  # start sector, as fls -o wants
            except ValueError:
                continue
    return offsets


_FLS_ENTRY_CAP = 1000


def _parse_fls(output: str) -> list:
    """Parse `fls -r -p` output into entries.

    Each line looks like:  r/r 16-128-1:   Users/jcole/plan.txt
    A leading '* ' marks a deleted entry. The type prefix's first letter is
    'd' for directories.
    """
    entries = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        deleted = line.startswith("*")
        if deleted:
            line = line[1:].strip()

        parts = line.split("\t", 1)
        if len(parts) != 2:
            # Some builds use spaces; split on the first colon-space instead.
            if ":" in line:
                type_meta, _, name = line.partition(":")
                name = name.strip()
                is_dir = type_meta.strip().startswith("d")
            else:
                continue
        else:
            type_meta, name = parts[0], parts[1].strip()
            is_dir = type_meta.strip().startswith("d")

        entries.append({"name": name, "is_dir": is_dir, "deleted": deleted})
        if len(entries) >= _FLS_ENTRY_CAP:
            break
    return entries


def _fmt_time(value):
    if not value:
        return ""
    try:
        import datetime
        return datetime.datetime.utcfromtimestamp(int(value)).strftime(
            "%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError, TypeError):
        return str(value)


def _port_pair(sport, dport):
    if sport and dport:
        return f"{sport} to {dport}"
    return ""
