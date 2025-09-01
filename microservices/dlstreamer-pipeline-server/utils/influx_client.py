#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

""" Influx Client for publishing the metadata to influxDB.
"""
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from src.publisher.influx.influx_schema import DataSchema
from src.common.log import get_logger
import urllib3

class InfluxClient():
    """Influx Client.
    """

    def __init__(self, host, port, influx_org, username, password):
        """Constructor
        """
        self.log = get_logger('Influx_Client')
        self.log.debug(f"In {__name__}...")
        self.host = host
        self.port = port
        self.influx_org = influx_org
        self.username = username
        self.password = password
        self.influx_endpoint_url = f"http://{self.host}:{self.port}"
        self.client = InfluxDBClient(url=self.influx_endpoint_url,username=self.username,password=self.password)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.schema = DataSchema()

    def upload_metadata(self, influx_bucket_name, point, img_handle):
        """Uploads frame data to influx storage

        :param influx_bucket_name: bucket_name 
        :type: string
        :param point: point data to be uploaded
        :type: Point
        :param img_handle: image handle for the frame
        :type: string
        """
        try:
            self.write_api.write(bucket=influx_bucket_name, org=self.influx_org, record=point)
            self.log.debug(f"Successfully wrote data in influx for image handle: {img_handle}")
        except urllib3.exceptions.NameResolutionError as e:
            self.log.exception("Unable to resolve InfluxDB hostname. Please verify that InfluxDB is running.")
        except Exception as e:
            self.log.exception(f"Error writing data to InfluxDB for image handle: {img_handle}", e)

    def get_point_data(self, metadata,influx_measurement):
        """Convert metadata to InfluxDB Point object

        :param metadata: frame metadata   
        :type: dict
        :param influx_measurement: measurement name
        :type: string
        """
        try:
            loaded = self.schema.load(metadata)
            result = self.schema.dump(loaded)
            image_handle = result.pop("img_handle", None)
            # The time stamp stored in influx is db write time, not the frame time.
            _ = result.pop("time", None)
            point = Point(influx_measurement).tag("img_handle", image_handle)
            for key, value in result.items():
                if value is not None:
                    point = point.field(key, value)
        except Exception as e:
            self.log.exception(f'Validation or processing error for image handle: {image_handle}', e)
        return point

    def publish(self, influx_bucket_name, influx_measurement, metadata):
        """Store metadata in influx storage

        :param influx_bucket_name: bucket name 
        :type: string
        :param influx_measurement: measurement name 
        :type: string
        :param metadata: metadata
        :type: json
        """
        # If this function is called, we are assuming the bucket is created
        point = self.get_point_data(metadata,influx_measurement)
        self.upload_metadata(influx_bucket_name, point,metadata.get("img_handle", "na"))
    
    def stop(self):
        """Stop influx Client
        """
        # for compatibility with other publisher.
        # TODO: Implement safe disconnect. 
        pass

    def bucket_exists(self, bucket_name):
        try:
            buckets_api = self.client.buckets_api()
            buckets = buckets_api.find_buckets().buckets
            return any(bucket.name == bucket_name for bucket in buckets)
        except:
            return False
