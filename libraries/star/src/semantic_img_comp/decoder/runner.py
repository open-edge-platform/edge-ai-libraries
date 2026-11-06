# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: decoder/runner.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: wrapper module that runs decoder functions.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from semantic_img_comp.decoder.demux import recv_frame
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge
from semantic_img_comp.net.connection import accept_clients
from semantic_img_comp.utils.logging_helpers import log_json
from semantic_img_comp.utils.logging_helpers import setup_logger
from semantic_img_comp.utils.runtime import sync
from semantic_img_comp.utils.service_http import STREAM_ID_PATTERN as _CLIENT_ID_PATTERN
from semantic_img_comp.utils.visualization import save_composite_img
from semantic_img_comp.utils.visualization import draw_boxes_on_pil


LOGGER = logging.getLogger(__name__)
_CLIENT_ID_RE = re.compile(_CLIENT_ID_PATTERN)


def _resolve_log_level(level_name: str | int) -> int:
    """Resolve textual or numeric logging levels with INFO fallback."""
    if isinstance(level_name, int):
        return level_name
    level_map = {
        "SILENT": logging.CRITICAL + 1,  # Above CRITICAL to suppress all logging
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    return level_map.get(str(level_name).upper(), logging.INFO)


def _handle_connection(conn, addr, *, cfg, bridge, decoder, logger, output_dir, recon_dir, client_id) -> None:
    """Receive and decode frames from one connected encoder until it disconnects.

    Runs in the main thread, one connection at a time -- the decoder/bridge are not
    built to be called concurrently from multiple connections, so a new connection
    is only accepted (see run_semantic_decoder's outer loop) after this one ends.

    Args:
        client_id: Stable identity received from the encoder's handshake (falls back
            to the socket address if the handshake was missing/empty); used for
            logging, output filenames, and the bridge's per-client frame sequencing.
    """
    # Raw receive count, independent of client_id: used only for the hang-check and
    # pre-decode error paths below, since decode_result.img_idx isn't available yet.
    received_count = 0
    try:
        while True:
            try:
                sync()
                t_start = time.perf_counter()

                payload = recv_frame(conn, cfg.mux_cfg)

                if payload is None:
                    log_json(logger, {
                        "event": "transmission_completed",
                        "client": client_id,
                        "frames_decoded": received_count,
                    })
                    break

                received_count += 1
                if received_count > 1_000_000:
                    raise RuntimeError("Abnormal frame count; possible connection hang")

                # Demux, decompress, and reconstruct via the shared codec bridge.
                try:
                    decode_result = bridge.decode_payload(payload, client_id=client_id)
                except Exception as exc:
                    cause = exc.__cause__ or exc
                    log_json(logger, {
                        "event": "frame_decode_failed",
                        "client": client_id,
                        "frame_id": received_count,
                        "error": str(exc),
                        "cause": str(cause),
                        "cause_type": type(cause).__name__,
                    })
                    LOGGER.exception("Frame decode exception detail:")
                    raise ValueError(f"Frame {received_count}: decode failed") from exc

                image_full = decode_result.image
                decode_time_ms = (time.perf_counter() - t_start) * 1000
                frame_id = decode_result.img_idx

                log_json(logger, {
                    "event": "frame_decoded",
                    "client": client_id,
                    "frame_number": frame_id,
                    "img_idx": frame_id,
                    "decode_time_ms": round(decode_time_ms, 2),
                    "num_crops": len(decode_result.crops) if decode_result.crops else 0,
                })

                # Save visualization if configured
                if cfg.io.save_visualizations:
                    try:
                        if cfg.io.annot_file:
                            img_name = decoder.img_names.get(decode_result.img_idx)
                            if not img_name:
                                img_name = f"{client_id}_{frame_id}.jpeg"
                            out_path = recon_dir / img_name
                        else:
                            out_path = recon_dir / f"{client_id}_{frame_id}.jpeg"

                        image_to_save = image_full
                        if decode_result.crops and getattr(cfg.io, "draw_bboxes", True):
                            image_to_save = draw_boxes_on_pil(
                                image_full.copy(),
                                decode_result.crops,
                                show_labels=False,
                            )

                        save_composite_img(image_to_save, out_path)

                        log_json(logger, {
                            "event": "visualization_saved",
                            "client": client_id,
                            "frame_id": frame_id,
                            "output_path": str(out_path),
                        })
                    except Exception as exc:
                        log_json(logger, {
                            "event": "visualization_save_failed",
                            "client": client_id,
                            "frame_id": frame_id,
                            "error": str(exc),
                        })
                        LOGGER.warning("Failed to save visualization for frame %d: %s", frame_id, exc)

            except ValueError as exc:
                log_json(logger, {
                    "event": "frame_processing_error",
                    "client": client_id,
                    "frame_number": received_count,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
                break

            except ConnectionError:
                log_json(logger, {
                    "event": "connection_lost",
                    "client": client_id,
                    "frame_number": received_count,
                })
                break

    finally:
        if hasattr(conn, "close"):
            conn.close()
        log_json(logger, {
            "event": "client_disconnected",
            "client": client_id,
            "frames_decoded": received_count,
        })


def run_semantic_decoder(cfg, host: str = "0.0.0.0", port: int = 5000, *, bridge: SemanticCodecBridge) -> None:  # nosec B104 - service is designed to run in a container and listen on all interfaces; host is operator-configurable
    """Run decoder pipeline: receive, demux, decompress, reconstruct, save.

    High-level flow:
    1) Listen for encoders on a TCP socket, accepting one connection at a time for
       the life of the process (an encoder restart/reconnect is handled by looping
       back to accept a new connection instead of exiting).
    2) For each received frame on the current connection:
       - Validate payload structure
       - Decompress background and objects
       - Reconstruct composite image
       - Save output if configured

    Args:
        cfg: Configuration object with io, img_process, etc.
        host: Listening address (default: all interfaces).
        port: Listening port.
        bridge: Pre-built SemanticCodecBridge (e.g. shared with the REST service side by the
            caller so both transports use the same decoder model instance and the same
            per-client frame sequencing). Required -- construct one shared instance and pass
            it in rather than letting it default to None.

    Raises:
        ValueError: If cfg.io.output_dir is invalid, or the recon output directory
            cannot be created.
    """
    if bridge is None:
        raise ValueError(
            "run_semantic_decoder requires a shared SemanticCodecBridge instance; "
            "construct one and pass it in instead of letting it default to None"
        )

    # Validate and create output directory
    try:
        output_dir = Path(cfg.io.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    except (AttributeError, TypeError, OSError) as exc:
        raise ValueError(f"cfg.io.output_dir must be a valid path, got {cfg.io.output_dir}") from exc

    logger = setup_logger(
        name="decoder",
        cfg=cfg,
    )

    # Setup decoder (built once, reused across every encoder connection).
    decoder = bridge.decoder

    # Create visualization output directories
    recon_dir = output_dir / "recon_images"
    try:
        recon_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, TypeError) as exc:
        log_json(logger, {
            "event": "decoder_output_dir_failed",
            "recon_dir": str(recon_dir),
            "error": str(exc),
        })
        raise

    log_json(logger, {
        "event": "decoder_started",
        "host": host,
        "port": port,
        "output_dir": str(output_dir),
    })

    try:
        for conn, addr in accept_clients(logger, host, port):
            # Handshake: read the encoder's stable client_id so saved files/logs survive
            # reconnects instead of being keyed on the (ephemeral) socket address.
            # The value is attacker-controlled wire input and is used to build output
            # file paths below, so it's validated against a safe-token pattern (same
            # one used for HTTP stream_id) to rule out path traversal (e.g. "../").
            addr_id = f"{addr[0]}:{addr[1]}"
            try:
                handshake = recv_frame(conn, cfg.mux_cfg)
            except (ConnectionError, OSError, ValueError):
                handshake = None
            client_id = handshake.decode("utf-8", errors="replace").strip() if handshake else ""
            if not client_id or not _CLIENT_ID_RE.match(client_id):
                client_id = addr_id

            _handle_connection(
                conn,
                addr,
                cfg=cfg,
                bridge=bridge,
                decoder=decoder,
                logger=logger,
                output_dir=output_dir,
                recon_dir=recon_dir,
                client_id=client_id,
            )
    except Exception as exc:
        log_json(logger, {
            "event": "decoder_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        raise
    finally:
        log_json(logger, {"event": "decoder_completed"})

