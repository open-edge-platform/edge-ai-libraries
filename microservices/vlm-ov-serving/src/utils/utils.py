# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import os
import random
import uuid
from io import BytesIO
from pathlib import Path
from typing import Dict, List

import aiohttp
import numpy as np
import openvino as ov
import torch
import yaml
from openvino_tokenizers import convert_tokenizer
from optimum.exporters.openvino.utils import save_preprocessors
from optimum.intel import (
    OVModelForCausalLM,
    OVModelForFeatureExtraction,
    OVModelForSequenceClassification,
    OVModelForVisualCausalLM,
)
from optimum.intel.utils.modeling_utils import _find_files_matching_pattern
from optimum.utils.save_utils import maybe_load_preprocessors
from PIL import Image
from src.utils.common import ErrorMessages, ModelNames, logger, settings
from src.utils.data_models import MessageContentVideoUrl
from transformers import AutoTokenizer

# Only include proxies if they are defined
proxies = {}
if settings.http_proxy:
    proxies["http"] = settings.http_proxy
if settings.https_proxy:
    proxies["https"] = settings.https_proxy
if settings.no_proxy_env:
    proxies["no_proxy"] = settings.no_proxy_env

logger.debug(f"proxies: {proxies}")


def convert_model(
    model_id: str, cache_dir: str, model_type: str = "vlm", weight_format: str = "int4"
):
    """
    Converts a specified model to OpenVINO format and saves it to the cache directory.

    Args:
        model_id (str): The identifier of the model to be converted.
        cache_dir (str): The directory where the converted model will be saved.
        model_type (str): The type of the model. It can be "embedding", "reranker", "llm", or "vlm".
        weight_format (str): The format of the model weights. Used for specific model types like "llm" and "vlm".
    Returns:
        None

    Raises:
        ValueError: If the model_type is not one of "embedding", "reranker", "llm", or "vlm".

    Notes:
        - If the model has already been converted and exists in the cache directory, the conversion process is skipped.
        - The function uses the Hugging Face `AutoTokenizer` to load and save the tokenizer.
        - The function uses OpenVINO's `convert_tokenizer` and `save_model` to convert and save the tokenizer.
        - Depending on the model_type, the function uses different OpenVINO model classes to convert and save the model:
            - "embedding": Uses `OVModelForFeatureExtraction`.
            - "reranker": Uses `OVModelForSequenceClassification`.
            - "llm": Uses `OVModelForCausalLM`.
            - "vlm": Uses `OVModelForVisualCausalLM`.
    """
    try:
        logger.debug(f"cache_ddir: {cache_dir}")
        if os.path.isdir(cache_dir):
            logger.info(f"Optimized {model_id} exist in {cache_dir}. Skip process...")
        else:
            logger.info(f"Converting {model_id} model to OpenVINO format...")
            hf_tokenizer = AutoTokenizer.from_pretrained(model_id)
            hf_tokenizer.save_pretrained(cache_dir)
            ov_tokenizer = convert_tokenizer(hf_tokenizer, add_special_tokens=False)
            ov.save_model(ov_tokenizer, f"{cache_dir}/openvino_tokenizer.xml")

            if model_type == "embedding":
                embedding_model = OVModelForFeatureExtraction.from_pretrained(
                    model_id, export=True
                )
                embedding_model.save_pretrained(cache_dir)
            elif model_type == "reranker":
                reranker_model = OVModelForSequenceClassification.from_pretrained(
                    model_id, export=True
                )
                reranker_model.save_pretrained(cache_dir)
            elif model_type == "llm":
                llm_model = OVModelForCausalLM.from_pretrained(
                    model_id, export=True, weight_format=weight_format
                )
                llm_model.save_pretrained(cache_dir)
            elif model_type == "vlm":
                vlm_model = OVModelForVisualCausalLM.from_pretrained(
                    model_id, export=True, weight_format=weight_format
                )
                vlm_model.save_pretrained(cache_dir)
                preprocessors = maybe_load_preprocessors(model_id)
                save_preprocessors(preprocessors, vlm_model.config, cache_dir, True)
            else:
                raise ValueError(f"Unsupported model type: {model_type}")
    except Exception as e:
        logger.error(f"Error occurred during model conversion: {e}")
        raise RuntimeError(f"Error occurred during model conversion: {e}")


async def load_images(image_urls_or_files: List[str]):
    """
    Load images from URLs, base64 strings, or file paths.

    Args:
        image_urls_or_files (List[str]): A list of image sources (URLs, base64 strings, or file paths).

    Returns:
        Tuple[List[Image.Image], List[ov.Tensor]]: A tuple containing a list of PIL images and a list of OpenVINO tensors.

    Raises:
        RuntimeError: If an error occurs while loading an image.
        ValueError: If the base64 data is invalid.
    """
    images = []
    image_tensors = []
    for image_url_or_file in image_urls_or_files:
        try:
            logger.info(
                f"Loading image from: {image_url_or_file if not image_url_or_file.startswith('data:image/jpeg;base64') else 'base64 image'}"
            )
            use_proxy = True
            if proxies.get("no_proxy"):
                no_proxy_list = proxies["no_proxy"].split(",")
                for no_proxy in no_proxy_list:
                    if no_proxy in image_url_or_file:
                        use_proxy = False
                        break

            if str(image_url_or_file).startswith("http"):
                proxy = proxies.get("http") if use_proxy else None
            elif str(image_url_or_file).startswith("https"):
                proxy = proxies.get("https") if use_proxy else None
            else:
                proxy = None

            if str(image_url_or_file).startswith("http") or str(
                image_url_or_file
            ).startswith("https"):
                logger.debug(f"Using proxy: {proxy}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        image_url_or_file, proxy=proxy, allow_redirects=True
                    ) as response:
                        response.raise_for_status()  # Raise an HTTPError for bad responses
                        image = Image.open(BytesIO(await response.read())).convert(
                            "RGB"
                        )
            elif str(image_url_or_file).startswith("data:image/jpeg;base64,"):
                decoded_image = base64.b64decode(image_url_or_file.split(",")[1])
                image = Image.open(BytesIO(decoded_image)).convert("RGB")
            else:
                image = Image.open(image_url_or_file).convert("RGB")
            image_data = (
                np.array(image.getdata())
                .reshape(1, image.size[1], image.size[0], 3)
                .astype(np.byte)
            )
            images.append(image)
            image_tensors.append(ov.Tensor(image_data))
        except aiohttp.ClientError as e:
            logger.error(f"{ErrorMessages.REQUEST_ERROR}: {e}")
            raise RuntimeError(f"{ErrorMessages.REQUEST_ERROR}: {e}")
        except base64.binascii.Error as e:
            if "Incorrect padding" in str(e):
                logger.error(f"Invalid input: {e}")
                raise ValueError("Invalid input: Incorrect padding in base64 data")
            else:
                logger.error(f"{ErrorMessages.LOAD_IMAGE_ERROR}: {e}")
                raise RuntimeError(f"{ErrorMessages.LOAD_IMAGE_ERROR}: {e}")
        except Exception as e:
            logger.error(f"{ErrorMessages.LOAD_IMAGE_ERROR}: {e}")
            raise RuntimeError(f"{ErrorMessages.LOAD_IMAGE_ERROR}: {e}")
    return images, image_tensors


def get_devices():
    """
    Retrieves a list of available devices from the OpenVINO core.

    Returns:
        list: A list of available device names.
    """
    core = ov.Core()
    device_list = core.available_devices

    return device_list


def get_device_property(device: str = ""):
    """
    Retrieves the properties of a specified device.

    Args:
        device (str): The name of the device to query. Defaults to an empty string.

    Returns:
        dict: A dictionary containing the properties of the device. The keys are property names,
            and the values are the corresponding property values. Non-serializable types are
            converted to strings. If a property value cannot be retrieved due to a TypeError,
            it is set to "UNSUPPORTED TYPE".
    """
    properties_dict = {}
    core = ov.Core()
    try:
        supported_properties = core.get_property(device, "SUPPORTED_PROPERTIES")
        for property_key in supported_properties:
            if property_key not in (
                "SUPPORTED_METRICS",
                "SUPPORTED_CONFIG_KEYS",
                "SUPPORTED_PROPERTIES",
            ):
                try:
                    property_val = core.get_property(device, property_key)

                    # Convert non-serializable types to strings
                    if not isinstance(
                        property_val, (str, int, float, bool, type(None))
                    ):
                        property_val = str(property_val)

                except TypeError:
                    property_val = "UNSUPPORTED TYPE"

                properties_dict[property_key] = property_val
    except RuntimeError:
        # Handle invalid device names
        logger.warning(f"Device '{device}' is not registered in the OpenVINO Runtime.")
        return {}

    return properties_dict


def is_model_ready(model_dir: Path) -> bool:
    """
    Check if the model is ready by verifying the existence of the OpenVINO model files.

    Args:
        model_dir (Path): The directory where the model is stored.

    Returns:
        bool: True if the model files exist, False otherwise.
    """
    ov_files = _find_files_matching_pattern(
        model_dir, pattern=r"(.*)?openvino(.*)?\_model(.*)?.xml$"
    )
    return bool(ov_files)


def load_model_config(
    model_name: str, config_path: Path = Path("src/config/model_config.yaml")
) -> Dict:
    """
    Load the configuration for a specific model from a YAML file.

    Args:
        model_name (str): The name of the model.
        config_path (Path): Path to the configuration file.

    Returns:
        dict: The configuration for the specified model.

    Raises:
        RuntimeError: If an error occurs while loading or parsing the configuration.
    """
    try:
        with open(config_path, "r") as config_file:
            configs = yaml.safe_load(config_file)
        config = configs.get(model_name.lower(), {})
        logger.info(f"Loaded configuration for model '{model_name}': {config}")
        return config
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML configuration: {e}")
        raise RuntimeError(f"Error parsing YAML configuration: {e}")
    except Exception as e:
        logger.error(f"Error loading model configuration: {e}")
        raise RuntimeError(f"Error loading model configuration: {e}")


def setup_seed(seed: int):
    """
    Set up the random seed for reproducibility.

    Args:
        seed (int): The seed value to use.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    logger.info(f"Random seed set to: {seed}")


def validate_video_inputs(content, model_name):
    """
    Validate video URL inputs based on the model name.

    Args:
        content: The content to validate (e.g., MessageContentVideoUrl).
        model_name: The name of the model.

    Returns:
        str: An error message if validation fails, otherwise None.
    """
    if (
        isinstance(content, MessageContentVideoUrl)
        and ModelNames.QWEN not in model_name.lower()
    ):
        return ErrorMessages.UNSUPPORTED_VIDEO_URL_INPUT
    return None


def decode_and_save_video(base64_video: str, output_dir: Path = Path("/tmp")) -> str:
    """
    Decode a base64-encoded video and save it locally.

    Args:
        base64_video (str): The base64-encoded video string.
        output_dir (Path): The directory to save the decoded video.

    Returns:
        str: The file path of the saved video.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        video_data = base64.b64decode(base64_video.split(",")[1])
        video_path = output_dir / f"{uuid.uuid4()}.mp4"
        with open(video_path, "wb") as video_file:
            video_file.write(video_data)
        logger.info(f"Video saved locally at: {video_path}")
        return f"file://{video_path}"
    except base64.binascii.Error as e:
        logger.error(f"Invalid base64 video data: {e}")
        raise ValueError("Invalid base64 video data")
    except Exception as e:
        logger.error(f"Error decoding and saving video: {e}")
        raise RuntimeError(f"Error decoding and saving video: {e}")
