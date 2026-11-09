# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: main.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: main wrapper to parse input args and run encoder or decoder.
"""
import argparse
import importlib
import logging
import os
import queue
import sys
import threading
from pathlib import Path
from time import sleep
from typing import Callable

# Threading env vars are set at container/runtime level (see Dockerfile).

from semantic_img_comp import healthcheck
from semantic_img_comp.image_feeder.feeder import start_image_feeder
from semantic_img_comp.utils.config import load_config
from semantic_img_comp.utils.load import load_paths_with_context
from semantic_img_comp.utils.load import load_paths_with_context
from semantic_img_comp.utils.logging_helpers import log_json, setup_logger
from semantic_img_comp.encoder.encoder import Encoder
from semantic_img_comp.decoder.decoder import Decoder
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge

LOGGER = logging.getLogger("semantic_img_comp.main")

EXIT_OK = 0
EXIT_BAD_ARGS = 2
EXIT_RUNTIME_ERROR = 1


def _valid_port(value: str) -> int:
    port = int(value)
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("--port must be between 1 and 65535")
    return port


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--fps must be >= 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=None,
        help="Input directory or YAML catalog file (.yml/.yaml) listing multiple image directories.",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument("--annot_file", type=str, default=None, help="Path to annotation file")
    parser.add_argument("--annot_dir", type=str, default=None, help="Path to directory with YOLO-style .txt annotation files (bypasses YOLO detection)")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument(
        "--skip-obj-detction",
        "--skip-obj-detection",
        action="store_true",
        dest="skip_obj_detection",
        help="Skip YOLO/object extraction/object compression and encode background only.",
    )
    parser.add_argument(
        "--role",
        type=str,
        choices=["encoder", "decoder"],
        required=True,
        help="Which side of the pipeline to run. Each role starts both the legacy batch "
             "TCP mode and the REST service concurrently (see README).",
    )
    parser.add_argument("--host", default="0.0.0.0")  # nosec B104 - service is designed to run in a container and listen on all interfaces; overridable via CLI
    parser.add_argument(
        "--target-input-rate-mbps",
        type=float,
        default=None,
        help="Target input data rate in Mbps (e.g., 1.1 for 1.1 Megabits per second)",
    )
    parser.add_argument(
        "--run-duration-sec",
        type=float,
        default=None,
        help="Stop the image feeder after this many seconds (e.g., 120 for 2 minutes). "
             "Encoder finishes processing any queued images after the feeder stops.",
    )

    parser.add_argument("--port", type=_valid_port, default=5000)
    parser.add_argument("--fps", type=_positive_float, default=0.0, help="Target send rate (frames/s). Use 0 to disable throttling.")
    parser.add_argument(
        "--canny-mode",
        choices=["old", "new"],
        default=None,
        help="Edge detector mode for mask-aware codecs: old (legacy) or new (canny-deriche).",
    )
    parser.add_argument(
        "--dlstreamer-pipeline-name",
        type=str,
        default=None,
        help="[encoder, detector_backend=dlstreamer] Which pipeline "
             "(configs/dlstreamer/config.json 'name') to invoke on the DL Streamer "
             "Pipeline Server, e.g. star_image_object_detection_npu to run detection "
             "on the NPU instead of the CPU-based default.",
    )
    parser.add_argument(
        "--decoder-url",
        type=str,
        default=None,
        help="[encoder] Base URL of the decoder's REST service to forward encoded payloads to, "
             "e.g. http://decoder:8000. Falls back to the DECODER_URL env var. Required for --role encoder.",
    )
    parser.add_argument(
        "--service-host",
        default="0.0.0.0",  # nosec B104 - service is designed to run in a container and listen on all interfaces; overridable via CLI
        help="Bind address for the REST service side of --role encoder/decoder.",
    )
    parser.add_argument(
        "--service-port",
        type=_valid_port,
        default=8000,
        help="Bind port for the REST service side of --role encoder/decoder.",
    )
    parser.add_argument(
        "--stream-buffer-size",
        type=int,
        default=200,
        help="[decoder REST service] Max decoded frames retained per stream before the oldest is evicted.",
    )
    parser.add_argument(
        "--client-id",
        type=str,
        default=None,
        help="[encoder] Stable identity sent to the decoder at the start of the TCP connection, "
             "so per-client frame sequencing survives encoder reconnects. Falls back to cfg.app.client_id.",
    )
    return parser


def _configure_logging(log_level_name: str, *, enable_stdout: bool = True) -> None:
    level_map = {
        "SILENT": logging.CRITICAL + 1,  # Above CRITICAL to suppress all logging
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    normalized_name = str(log_level_name).upper()
    level = level_map.get(normalized_name, logging.INFO)
    root = logging.getLogger()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    root.setLevel(level)

    stream_handlers = [
        handler
        for handler in list(root.handlers)
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
    ]

    should_print = bool(enable_stdout and normalized_name != "SILENT")
    if should_print:
        if not stream_handlers:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            root.addHandler(stream_handler)
        else:
            for handler in stream_handlers:
                handler.setFormatter(formatter)
    else:
        for handler in stream_handlers:
            root.removeHandler(handler)
            handler.close()


def _attach_root_file_logging(output_dir: Path, role: str) -> None:
    """Mirror root logger output to a role-specific log file for per-run persistence.

    Each role writes to its own file (app_enc.log / app_dec.log) using mode="w" so
    the file is reset on every run with no cross-process conflict.
    """
    filename = "app_enc.log" if role == "encoder" else "app_dec.log"
    root = logging.getLogger()
    log_path = Path(output_dir) / "log" / filename
    log_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_target = log_path.resolve()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            base_filename = getattr(handler, "baseFilename", None)
            if base_filename and Path(base_filename).resolve() == resolved_target:
                root.removeHandler(handler)
                handler.close()

    file_handler = logging.FileHandler(str(resolved_target), mode="w", encoding="utf-8")
    file_handler.setLevel(root.level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    )
    root.addHandler(file_handler)


def _apply_cli_overrides(cfg, args: argparse.Namespace) -> None:
    cfg.io.input_dir = Path(args.input) if args.input else Path(cfg.io.input_dir)
    cfg.io.output_dir = Path(args.output) if args.output else Path(cfg.io.output_dir)

    if args.annot_file:
        cfg.io.annot_file = Path(args.annot_file)
    elif cfg.io.annot_file:
        cfg.io.annot_file = Path(cfg.io.annot_file)

    if args.annot_dir:
        cfg.io.annot_dir = Path(args.annot_dir)
    elif getattr(cfg.io, "annot_dir", None):
        cfg.io.annot_dir = Path(cfg.io.annot_dir)
    else:
        cfg.io.annot_dir = None

    if args.target_input_rate_mbps is not None:
        cfg.image_feeder.target_input_rate_mbps = args.target_input_rate_mbps

    if args.run_duration_sec is not None:
        cfg.image_feeder.run_duration_sec = args.run_duration_sec

    if args.canny_mode is not None and hasattr(cfg, "img_process"):
        cfg.img_process.canny_mode = args.canny_mode

    if args.dlstreamer_pipeline_name is not None:
        cfg.model.dlstreamer_pipeline_name = args.dlstreamer_pipeline_name

    if args.client_id is not None:
        cfg.app.client_id = args.client_id

    cfg.model.skip_obj_detection = bool(args.skip_obj_detection)

    if args.skip_obj_detection:
        cfg.enc.obj_budget_ratio = 0.0



def _validate_runtime_paths(cfg, role: str, *, skip_obj_detection: bool = False) -> None:
    # Input images and annotations are consumed by the encoder only. The decoder receives
    # frames over the socket, so validating these for the decoder would reject valid runs
    # (e.g. a fresh checkout with no ./data directory).
    if role == "encoder":
        if cfg.io.annot_file and not cfg.io.annot_file.exists():
            raise FileNotFoundError(f"Annotation file does not exist: {cfg.io.annot_file}")

        if cfg.io.annot_dir and not cfg.io.annot_dir.is_dir():
            raise FileNotFoundError(f"Annotation directory does not exist: {cfg.io.annot_dir}")

        input_path = Path(cfg.io.input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")

        if input_path.is_dir():
            pass
        elif input_path.is_file() and input_path.suffix.lower() in {".yml", ".yaml"}:
            pass
        else:
            raise FileNotFoundError(
                f"Input must be an existing directory or YAML file, got: {input_path}"
            )

    cfg.io.output_dir.mkdir(parents=True, exist_ok=True)

    if role == "encoder" and not skip_obj_detection and not Path(cfg.model.enc_yolo_model_path).exists():
        LOGGER.warning("Model checkpoint does not exist yet: %s", cfg.model.enc_yolo_model_path)


def _run_encoder(cfg, host: str, port: int, fps: float, *, skip_obj_detection: bool, bridge=None) -> None:
    run_semantic_encoder = importlib.import_module(
        "semantic_img_comp.encoder.runner"
    ).run_semantic_encoder
    run_semantic_encoder(
        cfg,
        host,
        port,
        fps,
        skip_obj_detection=skip_obj_detection,
        bridge=bridge,
    )


def _run_decoder(cfg, host: str, port: int, *, bridge=None) -> None:
    run_semantic_decoder = importlib.import_module(
        "semantic_img_comp.decoder.runner"
    ).run_semantic_decoder
    run_semantic_decoder(cfg, host, port, bridge=bridge)


def _run_encoder_service(cfg, host: str, port: int, decoder_url: str, fps: float = 1.0, *, bridge=None) -> None:
    serve = importlib.import_module("semantic_img_comp.encoder.service").serve
    serve(cfg, host=host, port=port, decoder_url=decoder_url, bridge=bridge, fps=fps)


def _run_decoder_service(cfg, host: str, port: int, stream_buffer_size: int, *, bridge=None) -> None:
    serve = importlib.import_module("semantic_img_comp.decoder.service").serve
    serve(
        cfg,
        host=host,
        port=port,
        buffer_size=stream_buffer_size,
        output_dir=cfg.io.output_dir,
        save_visualizations=bool(cfg.io.save_visualizations),
        bridge=bridge,
    )


def _run_concurrently(name: str, targets: list[Callable[[], None]]) -> None:
    """Run every target in its own daemon thread.

    Returns once all targets finish normally (the steady-state case, since the REST
    service runs forever), or re-raises as soon as any target raises -- the other
    still-running daemon thread(s) are torn down when the process exits.
    """
    results: "queue.Queue[BaseException | None]" = queue.Queue()

    def _wrap(fn: Callable[[], None]) -> None:
        try:
            fn()
            results.put(None)
        except BaseException as exc:  # noqa: BLE001 - forwarded to the main thread below
            results.put(exc)

    threads = [
        threading.Thread(target=_wrap, args=(fn,), name=f"{name}-{i}", daemon=True)
        for i, fn in enumerate(targets)
    ]
    for t in threads:
        t.start()

    for _ in threads:
        exc = results.get()
        if exc is not None:
            raise exc

def _run_feeder(cfg, tcp_port: int, service_port: int) -> None:
    logger = setup_logger(
        name="feeder",
        cfg=cfg,
    )
    image_paths, input_paths_ctx = load_paths_with_context(
        cfg.io.input_dir,
        catalog_sampling_mode=getattr(cfg.io, "input_catalog_sampling", "uniform"),
    )
    feeder = start_image_feeder(
        image_paths,
        cfg,
        logger,
        input_paths_ctx.get("catalog_random_seed"),
    )

    mode = cfg.image_feeder.mode
    stream_id = cfg.app.client_id

    if mode == "tcp":
        feeder.feed_to_tcp("localhost", tcp_port, cfg, logger)
    elif mode == "http":
        feeder.feed_to_http(f"http://localhost:{service_port}", stream_id, logger)
    else:
        logger.warning("Unsupported image feeder mode: %s", mode)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        _configure_logging(cfg.app.log_level, enable_stdout=cfg.io.print_runtime_logs)
        healthcheck.start_status_server()

        _apply_cli_overrides(cfg, args)
        _validate_runtime_paths(cfg, args.role, skip_obj_detection=args.skip_obj_detection)

        if args.role == "encoder":
            decoder_url = args.decoder_url or os.getenv("DECODER_URL")
            if not decoder_url:
                raise ValueError(
                    "--decoder-url (or the DECODER_URL environment variable) is required for --role encoder"
                )
            bridge = SemanticCodecBridge(cfg, encoder=Encoder(cfg))
            _run_concurrently(
                "encoder",
                [
                    lambda: _run_encoder(
                        cfg,
                        args.host,
                        args.port,
                        args.fps,
                        skip_obj_detection=args.skip_obj_detection,
                        bridge=bridge,
                    ),
                    lambda: _run_encoder_service(
                        cfg, args.service_host, args.service_port, decoder_url, args.fps, bridge=bridge
                    ),
                    lambda: _run_feeder(cfg, args.port, args.service_port),
                ],
            )
        else:
            bridge = SemanticCodecBridge(cfg, decoder=Decoder(cfg))
            _run_concurrently(
                "decoder",
                [
                    lambda: _run_decoder(cfg, args.host, args.port, bridge=bridge),
                    lambda: _run_decoder_service(
                        cfg, args.service_host, args.service_port, args.stream_buffer_size, bridge=bridge
                    ),
                ],
            )
        return EXIT_OK
    except (FileNotFoundError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return EXIT_BAD_ARGS
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user")
        return EXIT_RUNTIME_ERROR
    except Exception:
        LOGGER.exception("Unhandled runtime error")
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
