#!/usr/bin/env python3

import argparse
import json
import os
import signal
import socket
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urlparse


# WS-Discovery multicast address and port defined by the ONVIF specification.
# 239.255.255.250 is the IPv4 multicast group used for WS-Discovery protocol,
# allowing automatic discovery of ONVIF-compliant network cameras on the local network.
# Port 3702 is the standard UDP port assigned by IANA for WS-Discovery.
MCAST_GRP = "239.255.255.250"
MCAST_PORT = 3702


@dataclass(frozen=True)
class DiscoveredCamera:
    ip: str
    port: Optional[int] = None


_STOP = False


def _handle_shutdown_signal(signum, frame):  # noqa: ARG001
    global _STOP
    _STOP = True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_probe_message(message_id: str) -> bytes:
    # Use a probe message compatible with a broad set of ONVIF devices.
    # Note: Types/Scopes are optional; many devices respond without them.
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<soap:Envelope xmlns:soap=\"http://www.w3.org/2003/05/soap-envelope\"
               xmlns:wsa=\"http://schemas.xmlsoap.org/ws/2004/08/addressing\"
               xmlns:tns=\"http://schemas.xmlsoap.org/ws/2005/04/discovery\"
               xmlns:dn=\"http://www.onvif.org/ver10/network/wsdl\">
  <soap:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>uuid:{message_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  </soap:Header>
  <soap:Body>
    <tns:Probe>
      <tns:Types>dn:NetworkVideoTransmitter</tns:Types>
    </tns:Probe>
  </soap:Body>
</soap:Envelope>""".encode("utf-8")


def _extract_xaddrs(xml_text: str) -> Optional[str]:
    # Try XML parse first.
    try:
        root = ET.fromstring(xml_text)
        for elem in root.iter():
            # Match any namespace: ...}XAddrs
            if elem.tag.endswith("XAddrs") and elem.text:
                return elem.text.strip()
    except Exception:
        pass

    # Fallback: cheap string search (works even if XML namespaces differ).
    if "XAddrs" not in xml_text:
        return None

    # Very small tolerant extraction
    start = xml_text.find("XAddrs")
    if start == -1:
        return None
    # Find closing tag
    close_tag = "</"
    close = xml_text.find(close_tag, start)
    if close == -1:
        return None
    # Find end of opening tag
    gt = xml_text.rfind(">", 0, start)
    if gt == -1:
        return None
    value = xml_text[gt + 1 : close].strip()
    return value or None


def _pick_best_xaddr(xaddrs: str) -> Optional[str]:
    # XAddrs may contain multiple URLs separated by whitespace.
    # Prefer ONVIF device service endpoint when present.
    candidates = [c.strip() for c in xaddrs.split() if c.strip()]
    if not candidates:
        return None

    for c in candidates:
        if "/onvif/device_service" in c:
            return c
    # Prefer http(s)
    for c in candidates:
        if c.startswith("http://") or c.startswith("https://"):
            return c
    return candidates[0]


def _parse_port_from_xaddr(xaddr: Optional[str]) -> Optional[int]:
    if not xaddr:
        return None
    try:
        parsed = urlparse(xaddr)
        if parsed.port is not None:
            return parsed.port
        # Default ports based on scheme when not explicitly specified
        if parsed.scheme == "http":
            return 80
        elif parsed.scheme == "https":
            return 443
        return None
    except Exception:
        return None


def _discover_once(listen_seconds: float, verbose: bool) -> list[DiscoveredCamera]:
    probe_id = str(uuid.uuid4())
    probe = _build_probe_message(probe_id)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(5)

        sock.sendto(probe, (MCAST_GRP, MCAST_PORT))
        if verbose:
            print(
                f"Sent WS-Discovery Probe to {MCAST_GRP}:{MCAST_PORT} (uuid:{probe_id})",
                flush=True,
            )

        discovered: dict[str, DiscoveredCamera] = {}
        deadline = time.time() + listen_seconds
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                continue

            ip = addr[0]
            response = data.decode("utf-8", errors="ignore")
            xaddrs_raw = _extract_xaddrs(response)
            xaddr = _pick_best_xaddr(xaddrs_raw) if xaddrs_raw else None
            port = _parse_port_from_xaddr(xaddr)

            if ip not in discovered:
                discovered[ip] = DiscoveredCamera(ip=ip, port=port)
                if verbose:
                    print(f"Found {ip} port={port}", flush=True)

        return sorted(discovered.values(), key=lambda c: c.ip)
    finally:
        sock.close()


def _atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="ONVIF WS-Discovery agent (writes JSON results periodically)"
    )
    parser.add_argument(
        "--out", required=True, help="Output JSON path (e.g. /out/onvif_cameras.json)"
    )
    parser.add_argument(
        "--interval", type=float, default=10.0, help="Seconds between discovery runs"
    )
    parser.add_argument(
        "--listen-seconds",
        type=float,
        default=5.0,
        help="How long to listen for replies per run",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Log discoveries to stdout"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)

    if args.verbose:
        print(f"Starting ONVIF discovery agent, output={args.out}", flush=True)

    while not _STOP:
        started = time.time()
        cameras = _discover_once(args.listen_seconds, args.verbose)
        payload = {
            "generated_at": _now_iso(),
            "multicast": {"group": MCAST_GRP, "port": MCAST_PORT},
            "count": len(cameras),
            "cameras": [asdict(c) for c in cameras],
        }
        try:
            _atomic_write_json(args.out, payload)
        except Exception as e:
            print(
                f"ERROR: failed to write {args.out}: {e}", file=sys.stderr, flush=True
            )

        # Sleep the remaining interval time
        elapsed = time.time() - started
        sleep_for = max(0.0, args.interval - elapsed)
        end = time.time() + sleep_for
        while not _STOP and time.time() < end:
            time.sleep(0.2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
