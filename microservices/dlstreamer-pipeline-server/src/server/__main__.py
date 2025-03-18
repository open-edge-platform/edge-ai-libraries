#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#


import sys
import os
import connexion
from flask_cors import CORS
from src.server.common.utils import logging
from src.server.pipeline_server import PipelineServer

logger = logging.get_logger('main', is_static=True)
MAX_BODY_SIZE = int(os.getenv("MAX_BODY_SIZE", "10240"))

def main(options):
    try:
        app = connexion.App(__name__, port=options.port, specification_dir='rest_api/', server='tornado')
        app.add_api('dlstreamer-pipeline-server.yaml',
                    arguments={'title': 'Intel(R) DL Streamer Pipeline Server API'})
        # Ref: https://github.com/spec-first/connexion/blob/main/docs/cookbook.rst#cors-support
        # Enables CORS on all domains/routes/methods per https://flask-cors.readthedocs.io/en/latest/#usage
        CORS(app.app)
        logger.info("Starting Tornado Server on port: %s", options.port)
        app.run(port=options.port, server='tornado', max_body_size=MAX_BODY_SIZE)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Keyboard Interrupt or System Exit")
    except Exception as error:
        logger.error("Error Starting Tornado Server: %s", error)
    PipelineServer.stop()
    logger.info("Exiting")

if __name__ == '__main__':
    try:
        PipelineServer.start()
    except Exception as error:
        logger.error("Error Starting Pipeline Server: %s", error)
        sys.exit(1)
    try:
        main(PipelineServer.options)
    except Exception as error:
        logger.error("Unexpected Error: %s", error)
