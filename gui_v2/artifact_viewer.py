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


def _render_network(path, log):
    from modules.network.pcap_parser import PCAPParser
    result = PCAPParser().parse(path)
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
    note = f"{result.get('packets', 0)} packets read"
    if len(rows) == 500:
        note += " (showing first 500)"
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
        # fls at the volume root: real filesystem listing from the image.
        result = runner.run_tsk(["fls", "-r", "-p", path], image_path=path)
    except Exception as error:
        return {"entries": [], "supported": True, "note": "",
                "error": f"couldn't read the image's filesystem: {error}"}

    if result.get("returncode", -1) != 0:
        stderr = (result.get("stderr") or "").strip()
        hint = ""
        if "not found" in stderr.lower():
            hint = (" SleuthKit binaries are needed to browse disk images; "
                    "they ship with the installer.")
        return {"entries": [], "supported": True, "note": "",
                "error": f"fls could not read this image: {stderr}{hint}"}

    entries = _parse_fls(result.get("stdout", ""))
    deleted = sum(1 for entry in entries if entry["deleted"])
    note = f"{len(entries)} entries"
    if deleted:
        note += f" · {deleted} deleted/recovered"
    if len(entries) == _FLS_ENTRY_CAP:
        note += f" (showing first {_FLS_ENTRY_CAP})"
    return {"entries": entries, "supported": True, "note": note, "error": ""}


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
