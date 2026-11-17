# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Align MPEG-TS continuity counters so a file can loop without demuxer errors.

Each PID needs a payload packet count that is a multiple of 16, so its
continuity counter wraps cleanly at the loop point. Missing packets are added
by splitting elementary-stream packets and repeating PAT/PMT packets. Payload
bytes are not changed.
"""

import argparse
from collections import defaultdict

TS_PACKET_SIZE = 188
SYNC_BYTE = 0x47
NULL_PID = 0x1FFF
PAT_PID = 0
SPLIT_PAYLOAD_BYTES = 92


def _pid(packet):
    return ((packet[1] & 0x1F) << 8) | packet[2]


def _payload(packet):
    if packet[3] & 0x20:
        return packet[5 + packet[4] :] if packet[3] & 0x10 else b""
    return packet[4:]


def _pmt_pids(packets):
    for packet in packets:
        if _pid(packet) == PAT_PID and packet[1] & 0x40:
            body = _payload(packet)
            section = body[1 + body[0] :]
            length = ((section[1] & 0x0F) << 8) | section[2]
            return {
                ((section[i + 2] & 0x1F) << 8) | section[i + 3]
                for i in range(8, 3 + length - 4, 4)
                if (section[i] << 8 | section[i + 1]) != 0
            }
    raise ValueError("no PAT found")


def _split(packet, keep=SPLIT_PAYLOAD_BYTES):
    """Split a payload-only packet into two packets with stuffing, keeping all bytes."""
    body = packet[4:]
    first_stuff = 183 - keep
    second_len = 184 - keep
    second_stuff = 183 - second_len

    def header_with_adaptation(stuff):
        head = bytearray(packet[:4])
        head[3] = (head[3] & 0xCF) | 0x30
        adapt = bytes([stuff]) + (
            b"\x00" + b"\xff" * (stuff - 1) if stuff >= 1 else b""
        )
        return bytes(head) + adapt

    first = header_with_adaptation(first_stuff) + body[:keep]
    second = header_with_adaptation(second_stuff) + body[keep:]
    assert len(first) == TS_PACKET_SIZE and len(second) == TS_PACKET_SIZE
    return first, second


def align(src, dst):
    """Write an aligned copy of ``src`` to ``dst`` and return a summary dict."""
    with open(src, "rb") as handle:
        data = handle.read()
    if len(data) % TS_PACKET_SIZE:
        raise ValueError("input size is not a multiple of 188 bytes")
    packets = [
        data[i : i + TS_PACKET_SIZE] for i in range(0, len(data), TS_PACKET_SIZE)
    ]
    for index, packet in enumerate(packets):
        if packet[0] != SYNC_BYTE:
            raise ValueError("sync loss at packet %d" % index)

    psi_pids = {PAT_PID} | _pmt_pids(packets)
    counts = defaultdict(int)
    psi_index = defaultdict(list)
    splittable = defaultdict(list)
    for index, packet in enumerate(packets):
        pid = _pid(packet)
        if pid == NULL_PID:
            continue
        if packet[3] & 0x10:
            counts[pid] += 1
        if pid in psi_pids:
            psi_index[pid].append(index)
        elif (
            (packet[3] & 0xF0) == 0x10
            and not (packet[1] & 0x40)
            and not (packet[3] & 0xC0)
            and index > 0
        ):
            splittable[pid].append(index)

    split_at = set()
    repeat_at = set()
    for pid, count in counts.items():
        deficit = (-count) % 16
        if not deficit:
            continue
        candidates = psi_index[pid] if pid in psi_pids else splittable[pid]
        if len(candidates) < deficit:
            raise ValueError("not enough packets to pad pid %d" % pid)
        step = len(candidates) // deficit
        chosen = {candidates[j * step] for j in range(deficit)}
        (repeat_at if pid in psi_pids else split_at).update(chosen)

    out = []
    for index, packet in enumerate(packets):
        if index in split_at:
            out.extend(_split(packet))
        else:
            out.append(packet)
        if index in repeat_at:
            out.append(packet)

    state = {}
    final = defaultdict(int)
    result = bytearray()
    for packet in out:
        packet = bytearray(packet)
        pid = _pid(packet)
        if pid != NULL_PID:
            current = state.get(pid)
            if packet[3] & 0x10:
                current = 0 if current is None else (current + 1) & 0x0F
                state[pid] = current
                final[pid] += 1
            elif current is None:
                current = 0
            packet[3] = (packet[3] & 0xF0) | current
        result.extend(packet)

    if any(count % 16 for count in final.values()):
        raise ValueError("alignment failed: counts not multiples of 16")
    with open(dst, "wb") as handle:
        handle.write(result)
    return {
        "packets": len(result) // TS_PACKET_SIZE,
        "bytes": len(result),
        "splits": len(split_at),
        "repeats": len(repeat_at),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Align MPEG-TS continuity counters for looping."
    )
    parser.add_argument("src")
    parser.add_argument("dst")
    args = parser.parse_args(argv)
    report = align(args.src, args.dst)
    print(
        "wrote %s: %d packets, %d bytes, %d splits, %d PSI repeats"
        % (
            args.dst,
            report["packets"],
            report["bytes"],
            report["splits"],
            report["repeats"],
        )
    )


if __name__ == "__main__":
    main()
