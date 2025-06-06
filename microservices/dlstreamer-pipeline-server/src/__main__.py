#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os
import json
import signal
import sys
import time
import threading
from distutils.util import strtobool

from src.manager import PipelineServerManager
from src.config import PipelineServerConfig
from src.common.log import get_logger
from src.rest_api.server import RestServer
from src.model_updater import ModelRegistryClient
from src.opentelemetry.opentelemetryexport import OpenTelemetryExporter

VERSION = "3.1.0"
EII_MODE = True if os.getenv('RUN_MODE') == "EII" else False

if EII_MODE:
    from utils import lem

rest_server = None
pipeline_server_mgr = None
lic_handler = None
otel_exporter = None

def release_license():
    if lic_handler is not None and (os.getenv("LICENSE_ENABLED", "").lower() == "true"):
        lic_handler.can_exit.set()
        lic_handler.stop()

def exit_handler():
    release_license()   # if license check enabled
    global rest_server
    global pipeline_server_mgr
    global otel_exporter
    if rest_server is not None:
        log.info("Stopping REST server")
        # rest_server.stop()    # currently no way to get a handle to the tornado server to stop it
        # log.info("REST server stopped")
    if pipeline_server_mgr is not None:
        log.info("Stopping Pipeline Server Manager")
        pipeline_server_mgr.stop()
        log.info("Pipeline Server Manager stopped")
    if otel_exporter is not None:
        log.info("Stopping OpenTelemetry Exporter")
        otel_exporter.stop()
    log.info("DL Streamer Pipeline Server exiting...")
    os._exit(-1)    # exit the process


def sig_cleanup_handler(sig, *args):
    log.info("Received signal: {}".format(sig))
    exit_handler()


signal.signal(signal.SIGINT, sig_cleanup_handler)
signal.signal(signal.SIGTERM, sig_cleanup_handler)
signal.signal(signal.SIGABRT, sig_cleanup_handler)


def watch_file_cbfunc():
    log.info('Config file has been updated, restarting DL Streamer Pipeline Server with latest cofig ')
    exit_handler()


def callback_func(key, _json):
    log.info('key {} has been updated in ETCD, restarting DL Streamer Pipeline Server with latest config '.format(key))
    exit_handler()
    

def main(cfg: PipelineServerConfig):
    # stop the server and any threads (for etcd change scenario in eii mode)
    # define pipeline server and pipelines
    # start REST server in a new thread -> start/stop/discover pipelines
    # monitor for exceptions and handle

    # stop the server, if running
    global rest_server
    global pipeline_server_mgr
    global otel_exporter
    
    if pipeline_server_mgr is not None:
        if not isinstance(pipeline_server_mgr, PipelineServerManager):
            raise ValueError("Invalid pipeline server manager instance")
        log.info("Restarting Pipeline Server Manager")
        if not pipeline_server_mgr.pserv._stopped:  # accessing private attribute, better solution ?
            pipeline_server_mgr.stop()  # set event to stop the server, any sub threads as well
        
    # stop rest server thread
    if rest_server is not None:
        log.info("joining rest server thread")
        rest_server.stop()
        log.info("joined !!!")
    
    if otel_exporter is not None:
        otel_exporter.stop()
        log.info("OpenTelemetry Exporter stopped")
        
    log.info("DL Streamer Pipeline Server Configuration:")
    app_cfg = cfg.get_app_config()
    log.info(json.dumps(app_cfg,indent=4))

    model_registry_cfg = cfg.get_model_registry_config()
    model_registry_client = None
    if model_registry_cfg:
        model_registry_client = ModelRegistryClient(model_registry_cfg=model_registry_cfg)
        model_registry_client.start_download_models(pipelines_cfg=cfg.get_pipelines_config())
        model_path_dict = model_registry_client.get_model_path(cfg.get_pipelines_config())
        log.info("Model Path Dict: {}".format(model_path_dict))
        if model_path_dict:
           cfg.update_pipeline_config(model_path_dict)

    # define pipeline server and pipelines
    pipeline_server_mgr = PipelineServerManager(cfg,pipeline_root="/var/cache/pipeline_root")

    pipeline_server_mgr.start()
    log.info("Pipeline Server Manager started")

    # start rest api server
    try:
        rest_server = RestServer(pipeline_server_mgr, model_registry_client)
        rest_server.start()
    except Exception as e:
        log.error('Exception in starting REST server: {}'.format(e))
        log.warning("REST Server Unavailable.")
        if rest_server is not None:
            rest_server.stop()
        #exit_handler()

    # identify load pipelines
    loaded_pl = pipeline_server_mgr.get_loaded_pipelines()
    log.info("="*10+" Loaded pipelines:  "+"="*10)
    for pl in loaded_pl:
        log.info("{}".format(pl))
    log.info("="*40)

    # start opentelemetry exporter
    if strtobool(os.getenv("ENABLE_OPEN_TELEMETRY","false")):
        otel_exporter = OpenTelemetryExporter()
        # Start the metrics collection in a separate thread
        otel_exporter.start()

    # monitor for rest server to stop
    if rest_server is not None:
        while True:
            if rest_server.done:            
                rest_server.stop()  # ensure blocking calls are stopped
                log.info("REST API server thread joined")
                log.warning("REST Server Unavailable.")
                break
            time.sleep(0.1)

    # main thread idling
    while True:        
        if pipeline_server_mgr is None:
            log.info("Pipeline Server Manager is None. breaking")
            break
        log.info("Main thread sleeping...")
        time.sleep(1.0)


if __name__ == "__main__":    
    
    try:
        log = get_logger(__name__)        
        
        if EII_MODE:
            lic_handler = lem.LicenseHandler()
            lic_handler.start_license_check()

        log.info("DL Streamer Pipeline Server version: {}".format(VERSION))
        cfg = PipelineServerConfig(mode=EII_MODE, watch_cb=callback_func, watch_file_cbfunc=watch_file_cbfunc)
        main(cfg)
        while True:
            log.info("sleeping...")
            time.sleep(1)   # TODO: wait for exception or signal to restart
    except Exception as e:
        log.exception("Exception in main. {}".format(e))
        log.info("Exiting...")
        exit_handler()
