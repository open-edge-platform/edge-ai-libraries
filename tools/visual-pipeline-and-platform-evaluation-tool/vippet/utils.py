import logging
import os
import re
import requests

logger = logging.getLogger("utils")

TEMP_DIR = "/tmp/"


def is_yolov10_model(model_path: str) -> bool:
    """
    Checks if the given model path corresponds to a YOLO v10 model.

    Args:
        model_path (str): Path to the model file.

    Returns:
        bool: True if the model is a YOLO v10 model, False otherwise.
    """
    return "yolov10" in model_path.lower()


def download_file(url, local_filename):
    file_path = os.path.join(TEMP_DIR, local_filename)
    if os.path.exists(file_path):
        logger.info(f"File {file_path} already exists, skipping download.")
        return file_path

    # Send a GET request to the URL
    with requests.get(url, stream=True) as response:
        response.raise_for_status()  # Check if the request was successful
        # Open a local file with write-binary mode
        with open(os.path.join(TEMP_DIR, local_filename), "wb") as file:
            # Iterate over the response content in chunks
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)  # Write each chunk to the local file
    return file_path


def replace_file_path(pipeline_description: str, file_path: str) -> str:
    # Replace after 'filesrc location='
    pipeline_description = re.sub(
        r"(filesrc\s+location=)[^\s!]+", rf"\1{file_path}", pipeline_description
    )
    # Replace after 'source='
    pipeline_description = re.sub(
        r"(source=)[^\s!]+", rf"\1{file_path}", pipeline_description
    )
    return pipeline_description
