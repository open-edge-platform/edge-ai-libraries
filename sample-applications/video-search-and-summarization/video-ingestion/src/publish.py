# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
from io import BytesIO

from PIL import Image

from rabbitmq_mqtt_client import RabbitMQMQTTClient  # Updated import
from minio_client import MinioClient


"""
PROLOGUE:
This Python script is used as the gstreamer element responsible for processing video frames, extracting metadata, publishing the data 
to RabbitMQ and storing image frames to Minio. This element is effectively the final sink element in the Gst pipeline. This is the 
reason the pipeline has `fakesink` as last element (just after this element) which does NOT do anything with the video/frames buffer reaching it. 
However, this does not mean that this particular pipeline is not handling the video/frames output.  
"""

Logger = logging.getLogger('PUBLISHER')
Logger.setLevel(logging.DEBUG)
class Publisher:
    """
    Publisher class responsible for processing video frames, extracting metadata, and publishing the data to RabbitMQ and Minio.
    Attributes:
        frame_id (int): The current frame ID.
        chunk_id (int): The current chunk ID.
        frames_per_chunk (int): Number of frames per chunk.
        bucket_name (str): The name of the Minio bucket.
        rabbitmq_client (RabbitMQMQTTClient): The RabbitMQ MQTT client instance.
        minio_client (MinioClient): The Minio client instance.
        messages (dict): Dictionary to store messages for each chunk.
    Methods:
        __init__(**kwargs): Initializes the publisher with the given parameters.
        __del__(): Cleans up resources before the object is destroyed.
        set_env_vars(): Sets environment variables for RabbitMQ and Minio.
        publish_current_chunk(): Publishes the current chunk's messages to RabbitMQ.
        process(frame): Processes each frame, extracts metadata, and saves the image and metadata to Minio.
        initialize_chunk_message(chunk_id): Initializes the message structure for a new chunk.
        update_metadata(metadata, video_info): Updates the metadata with image format information.
        save_image(image_array, image_filename, video_info, metadata): Saves the image to Minio Object storage.
        save_metadata(meta_filename, metadata, image_uri, chunk_id, chunk_frame_id): Saves the metadata in JSON format to Minio Object storage.
    """

    def __init__(self, *args, **kwargs):
        """
        Initializes the publisher with the given parameters.

        Args:
            args (list): A list containing frames per chunk and chunk duration for video
            kwargs (dict):
                chunk_duration (int): Duration of each chunk of video in seconds.
                video_identifier (str): A unique identifier for the video.
                topic (str): The MQTT topic to publish to.
        """
        Logger.info(f"Initializing Python Extension ...")
        self.get_env_vars()
        
        self.frame_id: int = 0
        self.chunk_id: int = 1
        self.topic: str = kwargs.get("topic")
        self.video_identifier: str = kwargs.get("video_identifier")
        self.bucket_name: str = kwargs.get("minio_bucket")
        

        if not self.topic or not self.video_identifier or not self.bucket_name:
            raise Exception("Missing required arguments: topic, video_identifier or bucket_name")
        
        if 1 < len(args):
            self.frames_per_chunk = args[0]
            self.chunk_duration = args[1]
        else:
            raise Exception("Missing required arguments: frame or chunk_duration")

        self.frame_interval: float = float(self.chunk_duration / self.frames_per_chunk)
        
        self.messages = {}  # Initialize messages attribute

        Logger.info("Connecting to RabbitMQ and Minio Client ...")
        self.rabbitmq_client = RabbitMQMQTTClient(self.mqtt_host, self.mqtt_port, self.mqtt_username, self.mqtt_passwd)
        self.minio_client = MinioClient.get_client(
            minio_server=self.minio_server, 
            access_key=self.minio_username, 
            secret_key=self.minio_passwd
        )
        
        if not self.rabbitmq_client.is_connected():
            Logger.error(f"Client is not connected to MQTT broker - {self.mqtt_host}:{self.mqtt_port}")
            return
        
        Logger.info("Module Initialization Done.")

    def __del__(self):
        if hasattr(self, "chunk_id") and hasattr(self, "messages"):
            self.publish_current_chunk()
        if hasattr(self, "rabbitmq_client"):
            self.rabbitmq_client.stop()

    def get_env_vars(self):
        try:
            self.mqtt_host: str = os.getenv("RABBITMQ_HOST", "localhost")
            self.mqtt_port: int = int(os.getenv("RABBITMQ_PORT", "1883"))
            self.minio_server: str = os.getenv("MINIO_SERVER", "localhost:9000")
            self.mqtt_username: str = os.getenv("RABBITMQ_DEFAULT_USER")
            self.mqtt_passwd: str = os.getenv("RABBITMQ_DEFAULT_PASS")
            self.minio_username: str = os.getenv("MINIO_ROOT_USER")
            self.minio_passwd: str = os.getenv("MINIO_ROOT_PASSWORD")
        except ValueError:
            raise Exception("Port value should be an integer.")

    def publish_current_chunk(self):
        """Publish the current chunk's messages."""
        if f"chunk_{self.chunk_id}" in self.messages:
            self.rabbitmq_client.publish(self.topic, json.dumps(self.messages[f"chunk_{self.chunk_id}"]))
            Logger.info(f"Published chunk {self.chunk_id}")

    def process(self, frame):
        """
        This callback is invoked for each frame that passes through gvapython.
        
        Args:
            frame (numpy.ndarray): The current frame (assumed in BGR format).
            
        Returns:
            bool: So the pipeline continues processing.
        """
        with frame.data() as image:
            video_info = frame.video_info()
            metadata = self.get_gva_metadata(frame.messages())

            chunk_frame_id = self.frame_id % self.frames_per_chunk + 1
            chunk_id = self.frame_id // self.frames_per_chunk + 1

            if chunk_id != self.chunk_id:
                Logger.info("publishing to rabbitmq")
                self.publish_current_chunk()
                self.chunk_id = chunk_id
                self.messages = {}  # Reset messages for the new chunk
            else:
                Logger.info(f'Skipping MQTT publish for frame {self.frame_id} as chunk ID has not changed.')

            self.initialize_chunk_message(chunk_id)

            image_filename = MinioClient.get_destination_file(
                video_id=self.video_identifier,
                chunk_id=chunk_id, 
                frame_id=chunk_frame_id, 
                file_type="frame"
            )

            meta_filename = MinioClient.get_destination_file(
                video_id=self.video_identifier,
                chunk_id=chunk_id, 
                frame_id=chunk_frame_id,
                file_type="metadata"
            )

            self.update_metadata(metadata, video_info)
            self.frame_id += 1
            image_uri = f"/{self.bucket_name}/{image_filename}"
            self.save_image(image, image_filename, metadata)
            self.save_metadata(meta_filename, metadata, image_uri, chunk_id, chunk_frame_id)

            self.messages[f"chunk_{chunk_id}"]["frames"].append({
                "frameId": self.frame_id,
                "chunkFrame": chunk_frame_id,
                "imageUri": image_uri,
                "metadata": metadata
            })

        return True

    def initialize_chunk_message(self, chunk_id):
        """Initialize the message structure for a new chunk."""
        if f"chunk_{chunk_id}" not in self.messages:
            self.messages[f"chunk_{chunk_id}"] = {
                "evamIdentifier": self.video_identifier,
                "chunkId": chunk_id,
                "frames": []
            }

    def get_gva_metadata(self, messages: list) -> dict:
        """Takes a list of frame meta messages, loads them as a JSON and 
        updates the metadata dict with the loaded JSON.
        """

        metadata: dict = {}
        for message in messages:
            message_json = json.loads(message)
            metadata.update(message_json)

        return metadata

    def update_metadata(self, metadata, video_info):
        """Update the metadata with color space format and frame timestamp."""

        # Add image color format
        image_format = video_info.to_caps().get_structure(0).get_value('format')
        metadata["img_format"] = image_format

        # Add timestamp at which frame occurs in the video
        
        metadata["frame_timestamp"] = float(self.frame_id * self.frame_interval)

    def save_image(self, image_array, image_filename, metadata):
        """Save the image to Minio Object storage."""
        
        # Invert the BGR color space to RGB
        if metadata.get("img_format") in ["BGR", "BGRx", "BGRA"]:
            image_array = image_array[:, :, 2::-1]

        image = Image.fromarray(image_array)
        image_buffer = BytesIO()
        image.save(image_buffer, format="JPEG", quality=85)
        MinioClient.save_object(
            self.minio_client,
            self.bucket_name, 
            object_name=image_filename,
            data=image_buffer
        )
            

    def save_metadata(self, meta_filename: str, metadata: dict, image_uri: str, chunk_id: int, chunk_frame_id: int):
        """Save the metadata in JSON format to Minio Object storage."""

        annotated_metadata = {
            "frame_id": self.frame_id,
            "chunk_id": chunk_id,
            "chunk_frame_number": chunk_frame_id,
            "image_uri": image_uri,
            "frame_metadata": metadata
        }

        metadata_dump: str = json.dumps(annotated_metadata)
        metadata_dump_bytes = metadata_dump.encode()
        length = len(metadata_dump_bytes)

        Logger.info(f'Saving metadata for frame {chunk_frame_id}')
        metadata_buffer = BytesIO(metadata_dump_bytes)

        MinioClient.save_object(
            self.minio_client, 
            self.bucket_name, 
            object_name=meta_filename,
            data=metadata_buffer, 
            length=length
        )
