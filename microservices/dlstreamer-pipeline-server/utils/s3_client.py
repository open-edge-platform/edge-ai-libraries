#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

""" S3 Client for connecting to broker and publishing messages.
"""

import boto3
import botocore
from src.common.log import get_logger

class S3Client():
    """S3 Client.
    """

    def __init__(self, host, port, s3_storage_user, s3_storage_pass, s3_folder_prefix):
        """Constructor
        """
        self.log = get_logger('S3_Client')
        self.log.debug(f"In {__name__}...")
        self.host = host
        self.port = port
        self.s3_folder_prefix = s3_folder_prefix
        self.s3_storage_user = s3_storage_user
        self.s3_storage_pass = s3_storage_pass

        self.s3_endpoint_url = f"http://{self.host}:{self.port}" 
        self.client = boto3.client(
            "s3",
            endpoint_url=self.s3_endpoint_url,
            aws_access_key_id=self.s3_storage_user,
            aws_secret_access_key=self.s3_storage_pass
        )

    def bucket_exists(self, s3_bucket_name):
        """Check if bucket exists in S3 storage

        :param s3_bucket_name: bucket_name 
        :type: string
        """
        try:
            self.client.head_bucket(Bucket=s3_bucket_name)
            return True
        except botocore.exceptions.ClientError:
            return False

    def upload_image_data(self, s3_bucket_name, object_name, frame_data, metadata=None):
        """Uploads frame data to S3 storage

        :param s3_bucket_name: bucket_name 
        :type: string
        :param object_name: name/ path of object (img_handle) 
        :type: string
        :param metadata: frame metadata (flat json only)    
        :type: dict
        """

        try:
            resp = self.client.put_object(
                Bucket=s3_bucket_name,
                Key=object_name,
                Body=frame_data
            )
            if not (resp['ResponseMetadata']['HTTPStatusCode'] == 200):
                self.log.error(f"Error uploading frame data: {object_name} to S3 storage")
            else:
                self.log.debug(f"Uploaded frame data at uri: s3://{s3_bucket_name}/{object_name} to S3 storage")
            
        except botocore.exceptions.ClientError as e:
            self.log.error(f"Error uploading frame data: {e}")

    def publish(self, s3_bucket_name, object_name, payload):
        """Store frame in S3 storage

        :param s3_bucket_name: bucket name 
        :type: string
        :param payload: Frame blob
        :type: json
        """
        
        ## If this function is called, we are assuming the bucket is created
        ## In cae the bucket is not created, this function will never be called. It will return from the S3Writer _publish method
        self.upload_image_data(s3_bucket_name=s3_bucket_name, object_name=object_name, frame_data=payload, metadata=None)
    
    def stop(self):
        """Stop S3 Client
        """
        # for compatibility with other publisher.
        # TODO: Implement safe disconnect. 
        pass
