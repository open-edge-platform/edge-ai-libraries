# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""``python -m adaptive_token_compressor.model_servers.lingua`` entry.

Thin shell over ``app.py`` so module-mode and Docker standalone-mode share one
argparse / one ``start_server``. Docker COPYs ``app.py`` directly and bypasses
this file.
"""
from adaptive_token_compressor.model_servers.lingua.app import (
    _parse_args,
    start_server,
)


def main() -> None:
    start_server(_parse_args())


if __name__ == "__main__":
    main()
