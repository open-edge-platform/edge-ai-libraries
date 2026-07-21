#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

""" Custom user defined function for anomaly detection on 
the windturbine speed and generated power data. """

import os
import logging
import pickle
import time
import math
import warnings
from kapacitor.udf.agent import Agent, Handler
from kapacitor.udf import udf_pb2
import numpy as np
from sklearnex import patch_sklearn, config_context
patch_sklearn()

warnings.filterwarnings(
    "ignore",
    message=".*Threading.*parallel backend is not supported by Extension for Scikit-learn.*"
)

warnings.filterwarnings(
    "ignore",
    message=".*X does not have valid feature names, but RandomForestRegressor was fitted with feature names*"
)




log_level = os.getenv('KAPACITOR_LOGGING_LEVEL', 'INFO').upper()
enable_benchmarking = os.getenv('ENABLE_BENCHMARKING', 'false').upper() == 'TRUE'
total_no_pts = int(os.getenv('BENCHMARK_TOTAL_PTS', "0"))
logging_level = getattr(logging, log_level, logging.INFO)

# Configure logging
logging.basicConfig(
    level=logging_level,  # Set the log level to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Log format
)

logger = logging.getLogger()

logging.getLogger("sklearnex").setLevel(logging.INFO)

# Anomaly detection on the windturbine speed and generated power data
class AnomalyDetectorHandler(Handler):
    """ Handler for the anomaly detection UDF. It processes incoming points
    and detects anomalies based on the wind speed and generated power data.
    """
    def __init__(self, agent):
        self._agent = agent
        # read the saved model and load it
        def load_model(filename):
            with open(filename, 'rb') as f:
                model = pickle.load(f)
            return model
        model_path = os.getenv('MODEL_PATH')
        model_path = os.path.abspath(model_path)
        self.rf = load_model(model_path)

        self.device = os.getenv('DEVICE', 'auto').lower()

        # wind speed and active power field name in the influxdb measurements
        self.x_name = "wind_speed"
        self.y_name = "grid_active_power"

        # hyper-params for anomaly classification
        self.error_threshold = 0.1
        self.anomalies = []
        self.cut_in_speed = 3
        self.cut_out_speed = 14
        self.min_power_th = 50

        self.points_received = {}
        global total_no_pts
        self.max_points = int(total_no_pts)

    def info(self):
        """ Return the InfoResponse. Describing the properties of this Handler
        """
        response = udf_pb2.Response()
        response.info.wants = udf_pb2.STREAM
        response.info.provides = udf_pb2.STREAM
        return response

    def init(self, init_req):
        """ Initialize the Handler with the provided options.
        """
        response = udf_pb2.Response()
        response.init.success = True
        return response

    def snapshot(self):
        """ Create a snapshot of the running state of the process.
        """
        response = udf_pb2.Response()
        response.snapshot.snapshot = b''
        return response

    def restore(self, restore_req):
        """ Restore a previous snapshot.
        """
        response = udf_pb2.Response()
        response.restore.success = False
        response.restore.error = 'not implemented'
        return response

    def begin_batch(self, begin_req):
        """ A batch has begun.
        """
        raise Exception("not supported")

    def point(self, point):
        """ A point has arrived.
        """
        logger.debug("Processing point %s", point.time)
        start_time = time.time_ns()
        check_for_anomalies = 1
        x = None
        y = None

        stream_src = None
        if "source" in point.tags:
            stream_src = point.tags["source"]
        elif "source" in point.fieldsString:
            stream_src = point.fieldsString["source"]


        global enable_benchmarking
        if enable_benchmarking:
            if stream_src not in self.points_received:
                self.points_received[stream_src] = 0
            if self.points_received[stream_src] >= self.max_points:
                return
            self.points_received[stream_src] += 1
        logger.debug("Processing point %s %s for source %s", point.time, time.time(), stream_src)

        def process_the_point(x,y):
            """Check if point is within valid operating range for anomaly detection."""
            if (math.isnan(x) or math.isnan(y)):
                return 0

            if ((x<=self.cut_in_speed) or (x>self.cut_in_speed and y<self.min_power_th)
                 or (x>self.cut_out_speed)):
                return 0

            return 1

        if self.x_name in point.fieldsDouble:
            x = np.float32(point.fieldsDouble[self.x_name])
 
        if self.y_name in point.fieldsDouble:
            y = np.float32(point.fieldsDouble[self.y_name])
 
        if x is not None and y is not None:
            # check if the current point is an anomalous point
            check_for_anomalies = process_the_point(x,y)
            point.fieldsDouble["analytic"] = True
 
            if check_for_anomalies:
                with config_context(target_offload=self.device,
                                            allow_fallback_to_host=True):
                    y_pred = self.rf.predict(np.array([x], dtype=np.float32).reshape(-1, 1))

                    # Relative error vs predicted (stable when actual power is near zero)
                    pred = np.float32(y_pred[0])
                    if pred > np.float32(0.0):
                        error = np.float32((pred - y) / pred)
                        if error > np.float32(self.error_threshold):
                            self.anomalies.append((x, y))
                            if error < np.float32(0.3):
                                point.fieldsDouble["anomaly_status"] = 0.3  # LOW
                            elif error < np.float32(0.6):
                                point.fieldsDouble["anomaly_status"] = 0.6  # MEDIUM
                            else:
                                point.fieldsDouble["anomaly_status"] = 1.0  # HIGH
        else:
            logger.error("No input received for %s %s, %s %s. Skipping anomaly detection."
                         , self.x_name, x, self.y_name, y)
            point.fieldsDouble["analytic"] = False

        # write data back to db if it is an anomaly point or there is an alarm for the point
        response = udf_pb2.Response()
        # Check if anomaly_status field exists, if not add it with default value
        if "anomaly_status" not in point.fieldsDouble:
            point.fieldsDouble["anomaly_status"] = 0.0

        time_now = time.time_ns()
        processing_time = time_now - start_time
        end_end_time = time_now - point.time
        point.fieldsDouble["processing_time"] = processing_time
        point.fieldsDouble["end_end_time"] = end_end_time
        response.point.CopyFrom(point)

        self._agent.write_response(response, True)

        end_time = time.time_ns()
        process_time = (end_time - start_time)/1000
        logger.debug("Function point took %.4f milliseconds to complete.", process_time)
        logger.info(f"Processing point {point}, Inference time: {processing_time/1000000} milliseconds, End to end time: {end_end_time/1000000} milliseconds")

    def end_batch(self, end_req):
        """ The batch is complete.
        """
        raise Exception("not supported")


if __name__ == '__main__':
    # Create an agent
    agent = Agent()

    # Create a handler and pass it an agent so it can write points
    h = AnomalyDetectorHandler(agent)

    # Set the handler on the agent
    agent.handler = h

    # Anything printed to STDERR from a UDF process gets captured
    # into the Kapacitor logs.
    agent.start()
    agent.wait()