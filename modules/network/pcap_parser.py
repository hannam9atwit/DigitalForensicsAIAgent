"""
modules/network/pcap_parser.py

Reads a classic pcap capture into timeline events, read-only.

Two backends, chosen at runtime:
  * dpkt, if installed — full Ethernet/IP/TCP/UDP decode.
  * a pure-stdlib fallback otherwise — parses the classic pcap container and
    decodes Ethernet + IPv4 + TCP/UDP headers by hand, which is enough for the
    timeline's needs (time, src, dst, protocol, ports). This means pcap
    support does not depend on a third-party package being present in the
    frozen build.

pcapng (the newer block-based format) is NOT handled by the fallback; if a
pcapng file arrives without dpkt, the parser says so honestly via the returned
"error" field rather than producing zero events silently.

The parser never executes anything and opens the file read-only.

Return shape (matches the pipeline's event contract):
    {"events": [ {timestamp, source, type, label, path, sev,
                  src_ip, dst_ip, proto, sport, dport}, ... ],
     "packets": <int>,
     "error": <str or "">}
"""

import socket
import struct

# Classic pcap magic numbers (little- and big-endian, us and ns resolution).
_PCAP_MAGICS = {
    0xA1B2C3D4: ("<", 1_000_000),      # microsecond, little-endian
    0xD4C3B2A1: (">", 1_000_000),      # microsecond, big-endian
    0xA1B23C4D: ("<", 1_000_000_000),  # nanosecond, little-endian
    0x4D3CB2A1: (">", 1_000_000_000),  # nanosecond, big-endian
}
_PCAPNG_MAGIC = 0x0A0D0D0A

_MAX_PACKETS = 50_000  # cap so a huge capture can't stall the pipeline

_PROTO_NAMES = {6: "TCP", 17: "UDP", 1: "ICMP"}


class PCAPParser:
    def parse(self, path: str) -> dict:
        if not path:
            return {"events": [], "packets": 0, "error": "no file path given"}

        try:
            with open(path, "rb") as capture:
                header = capture.read(4)
                if len(header) < 4:
                    return {"events": [], "packets": 0,
                            "error": "file too short to be a capture"}
                magic = struct.unpack("<I", header)[0]
                magic_be = struct.unpack(">I", header)[0]

                if magic in _PCAP_MAGICS or magic_be in _PCAP_MAGICS:
                    return self._parse_classic(path)
                if magic == _PCAPNG_MAGIC or magic_be == _PCAPNG_MAGIC:
                    return self._parse_pcapng(path)
                return {"events": [], "packets": 0,
                        "error": "not a recognized pcap/pcapng file"}
        except OSError as error:
            return {"events": [], "packets": 0, "error": f"cannot read file: {error}"}

    # ── dpkt path (used by both classic and pcapng when available) ────────────

    def _parse_with_dpkt(self, path: str) -> dict:
        import dpkt

        events = []
        packet_count = 0
        with open(path, "rb") as capture:
            reader = dpkt.pcap.Reader(capture)
            for timestamp, buffer in reader:
                packet_count += 1
                if packet_count > _MAX_PACKETS:
                    break
                event = self._event_from_dpkt(dpkt, timestamp, buffer)
                if event:
                    events.append(event)
        return {"events": events, "packets": packet_count, "error": ""}

    def _event_from_dpkt(self, dpkt, timestamp, buffer):
        try:
            eth = dpkt.ethernet.Ethernet(buffer)
        except (dpkt.dpkt.UnpackError, Exception):
            return None
        if not isinstance(eth.data, dpkt.ip.IP):
            return None
        ip = eth.data
        src = socket.inet_ntoa(ip.src)
        dst = socket.inet_ntoa(ip.dst)
        proto = _PROTO_NAMES.get(ip.p, str(ip.p))
        sport = getattr(ip.data, "sport", None)
        dport = getattr(ip.data, "dport", None)
        return self._make_event(timestamp, src, dst, proto, sport, dport)

    # ── pure-stdlib classic pcap path ─────────────────────────────────────────

    def _parse_classic(self, path: str) -> dict:
        # Prefer dpkt if it is importable — richer and battle-tested.
        try:
            import dpkt  # noqa: F401
            return self._parse_with_dpkt(path)
        except ImportError:
            pass

        events = []
        packet_count = 0
        with open(path, "rb") as capture:
            global_header = capture.read(24)
            if len(global_header) < 24:
                return {"events": [], "packets": 0, "error": "truncated pcap header"}

            magic = struct.unpack("<I", global_header[:4])[0]
            endian, time_divisor = _PCAP_MAGICS.get(
                magic, _PCAP_MAGICS.get(struct.unpack(">I", global_header[:4])[0],
                                        ("<", 1_000_000)))
            link_type = struct.unpack(endian + "I", global_header[20:24])[0]

            while True:
                record_header = capture.read(16)
                if len(record_header) < 16:
                    break
                ts_sec, ts_frac, cap_len, _orig_len = struct.unpack(
                    endian + "IIII", record_header)
                payload = capture.read(cap_len)
                if len(payload) < cap_len:
                    break

                packet_count += 1
                if packet_count > _MAX_PACKETS:
                    break

                timestamp = ts_sec + ts_frac / time_divisor
                event = self._event_from_bytes(payload, link_type, timestamp)
                if event:
                    events.append(event)

        return {"events": events, "packets": packet_count, "error": ""}

    def _event_from_bytes(self, data, link_type, timestamp):
        # link_type 1 = Ethernet; 101 = raw IP. Only these two are decoded by
        # the fallback (the common cases for saved captures).
        offset = 0
        if link_type == 1:
            if len(data) < 14:
                return None
            ether_type = struct.unpack(">H", data[12:14])[0]
            if ether_type != 0x0800:  # not IPv4
                return None
            offset = 14
        elif link_type != 101:
            return None

        ip_header = data[offset:]
        if len(ip_header) < 20:
            return None
        version_ihl = ip_header[0]
        if version_ihl >> 4 != 4:
            return None
        ihl = (version_ihl & 0x0F) * 4
        protocol = ip_header[9]
        src = socket.inet_ntoa(ip_header[12:16])
        dst = socket.inet_ntoa(ip_header[16:20])

        sport = dport = None
        transport = ip_header[ihl:]
        if protocol in (6, 17) and len(transport) >= 4:
            sport, dport = struct.unpack(">HH", transport[:4])

        proto = _PROTO_NAMES.get(protocol, str(protocol))
        return self._make_event(timestamp, src, dst, proto, sport, dport)

    def _parse_pcapng(self, path: str) -> dict:
        try:
            import dpkt  # noqa: F401
            return self._parse_with_dpkt(path)
        except ImportError:
            return {"events": [], "packets": 0,
                    "error": ("pcapng format needs the 'dpkt' package, which "
                              "isn't installed. Convert to classic pcap or "
                              "install dpkt for pcapng support.")}

    # ── shared event builder ──────────────────────────────────────────────────

    def _make_event(self, timestamp, src, dst, proto, sport, dport):
        endpoint = f"{src}:{sport}" if sport else src
        target = f"{dst}:{dport}" if dport else dst
        label = f"{proto} {endpoint} to {target}"
        # Outbound to a non-private destination is mildly more notable than
        # internal chatter; the interpreter refines this further.
        sev = 2 if not _is_private(dst) else 1
        return {
            "timestamp": int(timestamp),
            "source": "Network",
            "type": "packet",
            "label": label,
            "path": target,
            "sev": sev,
            "src_ip": src, "dst_ip": dst, "proto": proto,
            "sport": sport, "dport": dport,
        }


def _is_private(ip: str) -> bool:
    try:
        first, second = (int(part) for part in ip.split(".")[:2])
    except (ValueError, IndexError):
        return False
    return (first == 10
            or (first == 172 and 16 <= second <= 31)
            or (first == 192 and second == 168)
            or first == 127)
