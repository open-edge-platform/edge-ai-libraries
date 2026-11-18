# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
<udf_name>: Kapacitor stream UDF for the Time Series Analytics microservice.

<one-line description of what this UDF detects or classifies>

Copy this file to udfs/<udf_name>.py and fill in every TODO before packaging.
See references/patterns.md for the point() body that matches your use case.
"""
import logging

from kapacitor.udf.agent import Agent, Handler
from kapacitor.udf import udf_pb2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger()

# TODO: declare pattern-specific constants here (thresholds, window sizes, …)
# Example:
#   LOW, HIGH = 80.0, 150.0               # threshold pattern
#   SPIKE_THRESHOLD = 5.0                 # rate-of-change pattern
#   MODEL_PATH = "<path-to-model>"        # pretrained model pattern — read from config at init
#   DEVICE = "auto"                       # override in __init__ if needed


class UdfNameHandler(Handler):
    # TODO: rename this class to <CamelCaseUdfName>Handler

    def __init__(self, agent):
        self._agent = agent
        # TODO: add per-task state here if your pattern needs it.
        # Kapacitor keeps one UDF process alive per enabled task (not per
        # point), so instance attributes persist across point() calls.
        # Examples:
        #   self.previous_value = None            # rate-of-change pattern
        #   self.window = collections.deque(maxlen=30)  # rolling-stats pattern
        #   self.model = joblib.load(MODEL_PATH) if MODEL_PATH else None  # pretrained model

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
        # TODO: replace this body with the pattern-specific logic from
        # references/patterns.md.  Minimal skeleton:
        #
        #   value = point.fieldsDouble.get("REPLACE_WITH_FIELD_NAME")
        #   if value is None:
        #       logger.error("Expected double field 'REPLACE_WITH_FIELD_NAME' missing from point")
        #       return
        #   if <condition>:
        #       response = udf_pb2.Response()
        #       response.point.CopyFrom(point)
        #       logger.info("Flagged anomalous point: REPLACE_WITH_FIELD_NAME=%s", value)
        #       self._agent.write_response(response, True)
        raise NotImplementedError("fill in point() from references/patterns.md")

    def end_batch(self, end_req):
        raise Exception("not supported")


if __name__ == '__main__':
    agent = Agent()
    agent.handler = UdfNameHandler(agent)  # TODO: use your renamed Handler class
    agent.start()
    agent.wait()
