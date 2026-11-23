# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: net/connection.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: module that includes transport protocol interface functions.
"""

import socket
import time

from semantic_img_comp.utils.logging_helpers import log_json

def connect_with_retry(logger, host: str, port: int, retry_delay_s: float = 2.0) -> socket.socket:
    """
    Create a TCP socket connection to (host, port), retrying indefinitely until the server accepts.
    :param logger: logs connection details
    :param host: Decoder host (hostname or IP address).
    :param port: Decoder TCP port.
    :param retry_delay_s: Delay between retries when the connection is refused.
    :return: A connected TCP socket. Caller is responsible for closing it.
    """

    attempt = 0
    while True:
        attempt += 1
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
            log_json(logger, {
                "event": "connected",
                "host": host,
                "port": port,
                "attempt": attempt,
            })
            return sock
        except (ConnectionRefusedError, socket.gaierror):
            sock.close()
            log_json(logger, {
                "event": "decoder_not_ready",
                "host": host,
                "port": port,
                "attempt": attempt,
                "retry_in_s": retry_delay_s,
            })
            time.sleep(retry_delay_s)


def wait_for_client(logger, host: str, port: int) -> socket.socket:
    """
    Wait for client to connect.
    :param logger: logs connection details
    :param host: Decoder host (hostname or IP address).
    :param port: Decoder TCP port.
    :return: the connected socket to the encoder
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.listen(1)

        log_json(logger, {
            "event": "decoder_listening",
            "host": host,
            "port": port,
        })

        start_time = time.time()

        conn, addr = sock.accept()
    finally:
        sock.close()

    wait_time = time.time() - start_time

    # ---- Connection event ----
    log_json(logger, {
        "event": "connected",
        "client_ip": addr[0],
        "client_port": addr[1],
        "host": host,
        "port": port,
        "wait_time_sec": round(wait_time, 3)
    })

    return conn


def accept_clients(logger, host: str, port: int, backlog: int = 5):
    """Listen on (host, port) and yield one connected socket per incoming client, forever.

    Unlike wait_for_client() (single connection, listening socket closed right after),
    this keeps listening so any number of clients can connect concurrently; the caller
    is responsible for closing each yielded socket.
    """
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listen_sock.bind((host, port))
        listen_sock.listen(backlog)
        log_json(logger, {
            "event": "encoder_listening",
            "host": host,
            "port": port,
        })

        while True:
            conn, addr = listen_sock.accept()
            log_json(logger, {
                "event": "client_connected",
                "client_ip": addr[0],
                "client_port": addr[1],
                "host": host,
                "port": port,
            })
            yield conn, addr
    finally:
        listen_sock.close()
