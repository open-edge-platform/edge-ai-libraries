# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import socket

import pytest

from semantic_img_comp.net import connection


class _DummyLogger:
    def info(self, *args, **kwargs):
        return None


class _FakeConn:
    pass


class _FakeSocket:
    def __init__(self, conn):
        self.conn = conn
        self.bound = None
        self.listen_backlog = None
        self.closed = False

    def bind(self, addr):
        self.bound = addr

    def listen(self, backlog):
        self.listen_backlog = backlog

    def accept(self):
        return self.conn, ("127.0.0.1", 5001)

    def close(self):
        self.closed = True



def test_wait_for_client_closes_listening_socket(monkeypatch):
    fake_conn = _FakeConn()
    fake_sock = _FakeSocket(fake_conn)

    monkeypatch.setattr(connection.socket, "socket", lambda *args, **kwargs: fake_sock)
    monkeypatch.setattr(connection.time, "time", lambda: 100.0)

    conn = connection.wait_for_client(_DummyLogger(), "127.0.0.1", 5000)

    assert conn is fake_conn
    assert fake_sock.bound == ("127.0.0.1", 5000)
    assert fake_sock.listen_backlog == 1
    assert fake_sock.closed is True


class _FlakySocket:
    """Fake socket whose connect() raises a scripted sequence of errors before succeeding."""

    def __init__(self, errors):
        self._errors = list(errors)
        self.closed = False

    def connect(self, addr):
        if self._errors:
            raise self._errors.pop(0)

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "first_error",
    [ConnectionRefusedError(), socket.gaierror(-2, "Name or service not known")],
)
def test_connect_with_retry_retries_then_succeeds(monkeypatch, first_error):
    sockets = [_FlakySocket([first_error]), _FlakySocket([])]

    monkeypatch.setattr(connection.socket, "socket", lambda *args, **kwargs: sockets.pop(0))
    monkeypatch.setattr(connection.time, "sleep", lambda _seconds: None)

    result = connection.connect_with_retry(_DummyLogger(), "decoder", 5000, retry_delay_s=0)

    assert result.closed is False

