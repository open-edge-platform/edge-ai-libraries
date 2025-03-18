#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

""" REST Server.
"""
import os
import asyncio
import connexion
from flask_cors import CORS
import threading as th
import connexion
import ssl
from distutils.util import strtobool
from src.common.log import get_logger
from src.rest_api.endpoints import Endpoints

class RestServer:
    """ REST Server.
    """

    def __init__(self, pipeline_server_manager, model_registry_client=None):
        """Constructor
        """
        self.log = get_logger(f'{__name__}')
        self.done = False

        self.port = os.getenv('REST_SERVER_PORT')
        if self.port is None:
            raise ValueError('REST_SERVER_PORT environment variable not set')
        self.rest_request_max_body_size = 1024*1024 # 1 MB
        self.stop_ev = th.Event()
        self.pipeline_server_manager = pipeline_server_manager
        self.model_registry_client = model_registry_client

    def start(self):
        """Start the server.
        """
        self.log.debug('Starting server thread')
        self.th = th.Thread(target=self._run)
        self.th.start()

    def stop(self):
        """Stop the server.
        """
        if self.stop_ev.is_set():
            return
        self.stop_ev.set()
        self.th.join()
        self.th = None

    def error_handler(self, msg):
        self.log.error('Error in REST server thread: {}'.format(msg))
        self.done = True

    def _run(self):
        """Private thread run method.
        """
        self.log.debug('Server thread started')

        try:
            # TODO: Make this env variable part of config object created in __main__.py.
            HTTPS_MODE = strtobool(os.getenv('HTTPS', "false"))
            while not self.stop_ev.is_set():
                # Explicitly setting event loop for thread as
                # asyncio event loop is used by Tornado internally.
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                Endpoints.pipeline_server_manager = self.pipeline_server_manager
                Endpoints.model_registry_client = self.model_registry_client
                app = connexion.App(__name__, port=self.port,
                                    specification_dir='./',
                                    server='tornado')
                app.add_api('pipeline-server.yaml',
                            arguments={'title': 'Edge Video Analtytics Microservice REST API'})
                # Ref: https://github.com/spec-first/connexion/blob/main/docs/cookbook.rst#cors-support
                # Enables CORS on all domains/routes/methods per https://flask-cors.readthedocs.io/en/latest/#usage
                CORS(app.app)
                self.log.info("Starting Tornado Server on port: %s", self.port)
                ssl_context = None
                if HTTPS_MODE:
                    cert_file = "/run/secrets/EdgeVideoAnalyticsMicroservice_Server/public.crt"
                    key_file = "/run/secrets/EdgeVideoAnalyticsMicroservice_Server/private.key"
                    ca_file = "/run/secrets/EdgeVideoAnalyticsMicroservice_Server/ca.crt"

                    if os.path.exists(cert_file) and os.path.exists(key_file):
                        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                        ssl_context.load_cert_chain(cert_file,
                                                    key_file)

                        MTLS_VERIFICATION = strtobool(os.getenv('MTLS_VERIFICATION', "false"))
                        if MTLS_VERIFICATION:
                            ssl_context.load_verify_locations(ca_file)
                            ssl_context.verify_mode = ssl.CERT_REQUIRED
                            self.log.info("mTLS enabled.")
                        else:
                            self.log.info("TLS enabled.")

                        # Set the minimum TLS version to use if TLS v1.3 or higher is not available
                        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                        # Filter cipher suites to include:
                        # - ECDHE-RSA-AES256-GCM-SHA384 and ECDHE-ECDSA-AES256-GCM-SHA384 for use with TLSv1.2
                        # - TLS_AES_256_GCM_SHA384 for use with TLSv1.3
                        ssl_context.set_ciphers(
                            "ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:TLS_AES_256_GCM_SHA384"
                            )

                    else:
                        raise Exception("Invalid SSL/TLS Certifcates, unable to start the server")

                app.run(port=self.port, server='tornado',
                        max_body_size=self.rest_request_max_body_size,
                        ssl_options=ssl_context
                        )

        except Exception as e:
            self.error_handler(e)
