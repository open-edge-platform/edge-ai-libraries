#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from kapacitor.udf.agent import Agent, Handler, Server
from kapacitor.udf import udf_pb2
import logging
import os

log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,  # Set the log level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Log format
)

logger = logging.getLogger()

# Mirrors all points it receives back to Kapacitor
class MirrorHandler(Handler):
    def __init__(self, agent):
        self._agent = agent

    def info(self):
        response = udf_pb2.Response()
        response.info.wants = udf_pb2.STREAM
        response.info.provides = udf_pb2.STREAM
        return response

    def init(self, init_req):
        response = udf_pb2.Response()
        response.init.success = True
        return response

    def snapshot(self):
        response = udf_pb2.Response()
        response.snapshot.snapshot = b''
        return response

    def restore(self, restore_req):
        response = udf_pb2.Response()
        response.restore.success = False
        response.restore.error = 'not implemented'
        return response

    def begin_batch(self, begin_req):
        raise Exception("not supported")

    def point(self, point):
        temp = None
        if "temperature" in point.fieldsDouble:
            temp = point.fieldsDouble["temperature"]
            
        if temp is None or isinstance(temp, (int, float)) is False:
            logger.error(f"Invalid temperature data received - {temp}")
        else:
            logger.debug(f"Received temperature point data {temp}")
            if temp < 20 or temp > 25:
                response = udf_pb2.Response()
                response.point.CopyFrom(point)
                logger.info(f"Temperature {temp} is outside the range 20-25.")
                self._agent.write_response(response, True)

    def end_batch(self, end_req):
        raise Exception("not supported")

if __name__ == '__main__':
    # Create an agent
    agent = Agent()

    # Create a handler and pass it an agent so it can write points
    h = MirrorHandler(agent)

    # Set the handler on the agent
    agent.handler = h

    # Anything printed to STDERR from a UDF process gets captured
    # into the Kapacitor logs.
    agent.start()
    agent.wait()
