#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os
import argparse
import json
from distutils import util

def parse_options(args=None):

    parser = argparse.ArgumentParser(fromfile_prefix_chars='@',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--port", action="store", type=int,
                        dest="port", default=int(os.getenv('PORT', '8080')))
    parser.add_argument("--framework", action="store", dest="framework",
                        choices=['gstreamer', 'ffmpeg'],
                        default=os.getenv('FRAMEWORK', 'gstreamer'))
    parser.add_argument("--pipeline_dir", action="store", dest="pipeline_dir",
                        type=str, default=os.getenv("PIPELINE_DIR", 'pipelines'))
    parser.add_argument("--model_dir", action="store", dest="model_dir",
                        type=str, default=os.getenv("MODEL_DIR", 'models'))
    parser.add_argument("--network_preference", action="store",
                        dest="network_preference",
                        type=str, default=os.getenv('NETWORK_PREFERENCE', '{}'))
    parser.add_argument("--max_running_pipelines", action="store",
                        dest="max_running_pipelines",
                        type=int, default=int(os.getenv('MAX_RUNNING_PIPELINES', '-1')))
    parser.add_argument("--log_level", action="store",
                        dest="log_level",
                        choices=['INFO', 'DEBUG'], default=os.getenv('LOG_LEVEL', 'INFO'))
    parser.add_argument("--config_path", action="store",
                        dest="config_path",
                        default=os.getenv('CONFIG_PATH',
                                          os.path.join(os.path.dirname(__file__) + "/..")))
    parser.add_argument("--ignore_init_errors",
                        dest="ignore_init_errors",
                        action="store",
                        type=lambda x: bool(util.strtobool(x)),
                        default=bool(util.strtobool(os.getenv('IGNORE_INIT_ERRORS', 'false'))))
    parser.add_argument("--enable-rtsp",
                        dest="enable_rtsp",
                        action="store",
                        type=lambda x: bool(util.strtobool(x)),
                        default=bool(util.strtobool(os.getenv('ENABLE_RTSP', 'false'))))
    parser.add_argument("--rtsp-port", action="store", type=int,
                        dest="rtsp_port", default=int(os.getenv('RTSP_PORT', '8554')))
    parser.add_argument("--enable-webrtc",
                        dest="enable_webrtc",
                        action="store",
                        type=lambda x: bool(util.strtobool(x)),
                        default=bool(util.strtobool(os.getenv('ENABLE_WEBRTC', 'false'))))
    parser.add_argument("--webrtc-signaling-server", action="store",
                        dest="webrtc_signaling_server",
                        default=os.getenv('WEBRTC_SIGNALING_SERVER', 'ws://webrtc_signaling_server:8443'))
    parser.add_argument("--emit-source-and-destination",
                        dest="emit_source_and_destination",
                        help="Outputs source/destination endpoint access information into metadata "
                        "and REST response messages",
                        action="store",
                        type=lambda x: bool(util.strtobool(x)),
                        default=bool(util.strtobool(os.getenv('EMIT_SOURCE_AND_DESTINATION', 'false'))))

    if (isinstance(args, dict)):
        args = ["--{}={}".format(key, value)
                for key, value in args.items() if value]

    try:
        result = parser.parse_args(args)
        parse_network_preference(result)
    except Exception:
        print("Unrecognized argument passed to PipelineServer")
        parser.print_help()
        raise
    return result


def parse_network_preference(options):
    try:
        options.network_preference = json.loads(options.network_preference)
    except Exception:
        options.network_preference = {}
