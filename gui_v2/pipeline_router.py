"""
gui_v2/pipeline_router.py

Routes every evidence item to the correct parser, merges all events into one
unified timeline, then runs the existing reasoning (rule + anomaly) engines and
narrative generator over the merged set.

This is what lets the native GUI pull evidence from Windows artifacts —
Event Logs, Registry, Prefetch, Network (PCAP), and Email — in addition to the
original disk + browser support.

Every parser import is deferred and wrapped so a missing optional dependency
(python-evtx, regipy, dpkt, pyscca) degrades to a clear log line instead of
crashing the whole run.
"""

import datetime


def _disk(path, log):
    """Existing SleuthKit disk path → unified events."""
    out = []
    try:
        from modules.disk.timeline_builder import DiskTimelineBuilder
        from modules.timeline.correlation_engine import TimelineCorrelationEngine
        raw = DiskTimelineBuilder().build_timeline(path)
        unified = TimelineCorrelationEngine().correlate(raw.get("events", []), [], [], [])
        for e in unified["events"]:
            e.setdefault("source", "Disk")
            e.setdefault("sev", 1)
            e["label"] = e.get("label") or "Filesystem — " + (e.get("path") or "")[-70:]
        out = unified["events"]
    except Exception as e:
        log(f"[!] disk parse failed for {path}: {e}")
    return out, "SleuthKit fls/mmls"


def _browser(path, log):
    out = []
    try:
        from modules.browser.history_parser import HistoryParser
        from modules.browser.downloads_parser import DownloadsParser
        hp = HistoryParser().parse(path)
        for v in hp.get("visits", []):
            if v.get("visit_time"):
                out.append({"timestamp": int(v["visit_time"]), "source": "Browser",
                            "type": "visit", "sev": 1,
                            "label": "URL visit — " + (v.get("title") or v.get("url", ""))[:70],
                            "path": v.get("url", "")})
        dp = DownloadsParser().parse(path)
        for d in dp.get("downloads", []):
            if d.get("start_time"):
                out.append({"timestamp": int(d["start_time"]), "source": "Downloads",
                            "type": "download", "sev": 2,
                            "label": "Download — " + (d.get("target_path") or "")[-60:],
                            "path": d.get("target_path", "")})
    except Exception as e:
        log(f"[!] browser parse failed for {path}: {e}")
    return out, "history_parser / downloads_parser"


def _eventlog(path, log):
    try:
        from modules.windows.evtx_parser import EventLogParser
        r = EventLogParser().parse(path)
        if r.get("error"):
            log(f"[!] evtx: {r['error']}")
        return r.get("events", []), "evtx_parser (python-evtx)"
    except Exception as e:
        log(f"[!] evtx import/parse failed: {e}")
        return [], "evtx_parser"


def _registry(path, log):
    try:
        from modules.windows.registry_parser import RegistryParser
        r = RegistryParser().parse(path)
        if r.get("error"):
            log(f"[!] registry: {r['error']}")
        return r.get("events", []), "registry_parser (regipy)"
    except Exception as e:
        log(f"[!] registry import/parse failed: {e}")
        return [], "registry_parser"


def _prefetch(path, log):
    try:
        from modules.windows.prefetch_parser import PrefetchParser
        r = PrefetchParser().parse(path)
        return r.get("events", []), "prefetch_parser"
    except Exception as e:
        log(f"[!] prefetch parse failed: {e}")
        return [], "prefetch_parser"


def _network(path, log):
    try:
        from modules.network.pcap_parser import PCAPParser
    except Exception as error:
        log(f"[!] network parser unavailable: {error}")
        return [], "pcap_parser", f"parser unavailable: {error}"

    try:
        result = PCAPParser().parse(path)
    except Exception as error:
        log(f"[!] pcap parse failed: {error}")
        return [], "pcap_parser", f"parse failed: {error}"

    if result.get("error"):
        log(f"[!] pcap: {result['error']}")
        return result.get("events", []), "pcap_parser", result["error"]

    packets = result.get("packets", 0)
    return result.get("events", []), "pcap_parser", (
        f"{packets} packets read" if packets else "")


def _email(path, log):
    try:
        from modules.email_fx.mbox_parser import EmailParser
        r = EmailParser().parse(path)
        return r.get("events", []), "mbox_parser"
    except Exception as e:
        log(f"[!] email parse failed: {e}")
        return [], "mbox_parser"


ROUTES = {
    "disk": _disk, "browser": _browser, "eventlog": _eventlog,
    "registry": _registry, "prefetch": _prefetch, "network": _network,
    "email": _email, "unknown": _disk,
}


def run_analysis(evidence_list, log=print, ai_config=None):
    """
    evidence_list: list of dicts each with "_path" and "kind".
    ai_config: the user's engine choice from Settings (provider/model/api_key).
    Returns {events, findings, anomalies, narrative, pipeline}, where narrative
    is {"markdown": <text>, "ai_status": <who-drafted-it record>}.
    """
    import time
    t0 = time.time()
    all_events = []
    parser_status = []  # (artifact_id, name, kind, count, note) for the audit trail

    for ev in evidence_list:
        kind = ev.get("kind", "unknown")
        path = ev.get("_path")
        log(f"[*] Parsing {ev['id']} {ev['name']} ({kind})")
        parser = ROUTES.get(kind, _disk)

        # Routes may return (events, name) or (events, name, note). The note
        # carries a human-readable reason when a parser is missing, fails, or
        # simply finds nothing — so those outcomes reach the audit trail
        # instead of vanishing into the debug log.
        result = parser(path, log)
        note = ""
        if len(result) == 3:
            events, parser_name, note = result
        else:
            events, parser_name = result

        for e in events:
            e["artifact"] = ev["id"]
            e.setdefault("source", _src_for(kind))
        ev["events"] = len(events)
        ev["parser"] = parser_name
        ev["detail"] = f"{len(events)} events parsed"
        all_events += events

        if not events:
            reason = note or "no events produced"
            log(f"[!] {ev['id']} {ev['name']}: {reason}")
            parser_status.append(
                (ev["id"], parser_name, kind, 0, reason))
        else:
            parser_status.append(
                (ev["id"], parser_name, kind, len(events), note))

    all_events = [e for e in all_events if e.get("timestamp")]
    all_events.sort(key=lambda e: e["timestamp"])

    # interpret every event: category, plain-English description, relevance,
    # and a meaningful severity (fixes the "everything is LOW / Filesystem —"
    # problem and the wall of NTFS metadata noise).
    from .interpreter import enrich_events
    all_events, relevance_stats = enrich_events(all_events)
    log(f"[+] Interpreted events — "
        f"{relevance_stats.get('significant',0)} significant, "
        f"{relevance_stats.get('notable',0)} notable, "
        f"{relevance_stats.get('context',0)} context, "
        f"{relevance_stats.get('noise',0)} system-noise")
    log(f"[+] Unified timeline — {len(all_events)} events across "
        f"{len(evidence_list)} artifacts")

    # reasoning: reuse the v1 rule + anomaly engines on the merged events
    findings, anomalies = [], []
    try:
        from ai.rule_engine import RuleEngine
        from ai.anomaly_engine import AnomalyEngine
        disk_like = {"events": all_events}
        findings = RuleEngine().run(disk_like, {}, {"events": all_events})
        anomalies = AnomalyEngine().run(disk_like, {}, {"events": all_events})
    except Exception as e:
        log(f"[!] reasoning engines unavailable: {e}")

    # lightweight rules specific to the new sources — aggregated one finding
    # per pattern (not one per event), matching the rule engine's shape so a
    # log full of USB or service events stays a single readable finding.
    findings += _aggregate_source_findings(all_events)

    # MITRE + confidence
    try:
        from ai import ioc_matcher
        for f in findings:
            mid, mname = ioc_matcher.match(f.get("type", ""))
            f["mitre"], f["mitreName"] = mid, mname
            f["conf"] = ioc_matcher.confidence(f)
    except Exception:
        pass

    # No LLM in the deterministic pipeline: the case must open the instant
    # parsing and reasoning finish. All AI narrative — the report summary and
    # conclusion, the case overview, question answering — is produced by the
    # background deep dive (ai/deep_dive.py) and reasons from the digested
    # knowledge base, not a flat context dump. Until the dive runs, the narrative
    # slots stay empty and each surface shows its deterministic fallback.
    log("[+] Deterministic analysis complete — AI insights run in the background")

    dur = time.time() - t0
    return {
        "events": all_events, "findings": findings, "anomalies": anomalies,
        "narrative": {"markdown": "", "ai_status": None},
        "knowledge_base": [],
        "parserStatus": parser_status,
        "pipeline": {
            "lastRun": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": f"{int(dur//60)}m {int(dur % 60):02d}s",
            "eventsParsed": len(all_events), "status": "complete",
        },
    }


def _src_for(kind):
    return {"disk": "Disk", "browser": "Browser", "registry": "Registry",
            "eventlog": "EventLog", "prefetch": "Disk", "network": "Network",
            "email": "Email"}.get(kind, "Disk")


# Windows/registry event types that each collapse to one aggregated finding.
# (event type, finding type, severity, noun-builder(count)).
_SOURCE_RULES = [
    ("service", "service_installed", 3,
     lambda n: f"{n:,} service{'' if n == 1 else 's'} installed"),
    ("log_cleared", "history_gap", 4,
     lambda n: f"{n:,} log or history clear event{'' if n == 1 else 's'} recorded"),
    ("usb", "exfiltration_removable_media", 3,
     lambda n: f"{n:,} file{'' if n == 1 else 's'} written to removable media"),
]


def _aggregate_source_findings(all_events):
    """Collapse the per-event service/log-clear/USB rules into one finding each.

    Emitting one finding per matching event turned a busy event log into
    thousands of identical entries; this keeps each pattern a single finding
    carrying a count, time span and a small sample of labels — the same shape
    the rule engine produces.
    """
    def fmt(ts):
        try:
            return datetime.datetime.utcfromtimestamp(int(ts)).strftime(
                "%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, OSError, OverflowError, TypeError):
            return str(ts)

    buckets = {}
    for e in all_events:
        etype = e.get("type")
        if etype in ("service", "log_cleared", "usb"):
            buckets.setdefault(etype, []).append(e)

    findings = []
    for etype, ftype, severity, phrase in _SOURCE_RULES:
        events = buckets.get(etype)
        if not events:
            continue
        times = sorted(x["timestamp"] for x in events
                       if isinstance(x.get("timestamp"), int) and x["timestamp"] > 0)
        span = ""
        if times:
            span = (f" on {fmt(times[0])}" if times[0] == times[-1]
                    else f", spanning {fmt(times[0])} to {fmt(times[-1])}")
        labels = [x.get("label", "") for x in events if x.get("label")][:8]
        findings.append({
            "type":      ftype,
            "severity":  severity,
            "count":     len(events),
            "path":      f"{len(events):,} events",
            "timestamp": times[0] if times else events[0].get("timestamp"),
            "reason":    (f"{phrase(len(events))}{span}. Examples: "
                          f"{'; '.join(labels) if labels else 'none recorded'}."),
            "details":   {"count": len(events), "sample": labels,
                          "artifact": events[0].get("artifact")},
        })
    return findings
