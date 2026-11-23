# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import struct
import socket
from typing import cast

import pytest

from semantic_img_comp.decoder.demux import recv_exact, recv_frame
from semantic_img_comp.utils.config import MuxStructConfig


class _RecvOnlySocket:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def recv(self, _n):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _RecvIntoSocket:
    def __init__(self, chunks):
        self._chunks = [bytearray(chunk) for chunk in chunks]

    def recv_into(self, buffer, nbytes):
        if not self._chunks:
            return 0
        chunk = self._chunks[0]
        take = min(len(chunk), nbytes)
        buffer[:take] = chunk[:take]
        del chunk[:take]
        if not chunk:
            self._chunks.pop(0)
        return take


def _mux_cfg():
    return MuxStructConfig()


def test_recv_exact_uses_recv_into_path_and_reassembles_chunks():
    sock = _RecvIntoSocket([b"ab", b"cd", b"ef"])

    out = recv_exact(cast(socket.socket, cast(object, sock)), 6)

    assert out == b"abcdef"


def test_recv_exact_falls_back_to_recv_only_socket():
    sock = _RecvOnlySocket([b"ab", b"cd", b"ef"])

    out = recv_exact(cast(socket.socket, cast(object, sock)), 6)

    assert out == b"abcdef"


def test_recv_exact_returns_none_on_mid_stream_eof():
    sock = _RecvIntoSocket([b"ab"])

    out = recv_exact(cast(socket.socket, cast(object, sock)), 4)

    assert out is None


def test_recv_exact_rejects_negative_lengths():
    sock = _RecvOnlySocket([])

    with pytest.raises(ValueError, match="n must be >= 0"):
        recv_exact(cast(socket.socket, cast(object, sock)), -1)


def test_recv_frame_returns_payload_when_header_and_frame_arrive_in_chunks():
    payload = b"hello"
    header = struct.pack("!I", len(payload))
    sock = _RecvIntoSocket([header[:2], header[2:], payload[:2], payload[2:]])

    out = recv_frame(cast(socket.socket, cast(object, sock)), _mux_cfg())

    assert out == payload



