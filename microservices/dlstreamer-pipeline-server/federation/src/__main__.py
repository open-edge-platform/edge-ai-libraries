# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging

import uvicorn

from .config import load_config
from .proxy import create_app


def main():
    parser = argparse.ArgumentParser(
        description="DLS-PS Federation Proxy"
    )
    parser.add_argument(
        "--config", default="nodes.yaml", help="Path to node registry config"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=8080, help="Listen port")
    parser.add_argument(
        "--log-level", default="info", help="Log level (debug, info, warning, error)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    config = load_config(args.config)
    logging.getLogger(__name__).info(
        "Starting federation proxy with %d node(s)", len(config.nodes)
    )
    app = create_app(config)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
