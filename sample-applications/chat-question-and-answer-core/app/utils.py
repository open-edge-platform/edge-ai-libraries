import os
import openvino as ov
import openvino.properties as props
from .logger import logger
from huggingface_hub import login, whoami, snapshot_download
from optimum.intel import (
    OVModelForFeatureExtraction,
    OVModelForSequenceClassification,
    OVModelForCausalLM,
)
from transformers import AutoTokenizer
from openvino_tokenizers import convert_tokenizer


def login_to_huggingface(token: str):
    """
    Logs in to Hugging Face using the provided token and checks the authenticated user.

    Args:
        token (str): The authentication token for Hugging Face.

    Returns:
        None

    """

    logger.info("Logging in to Hugging Face...")

    login(token=token)

    # Check the authenticated user
    user_info = whoami()

    if user_info:
        logger.info(f"Logged in successfully as {user_info['name']}")
    else:
        logger.error("Login failed.")


def download_huggingface_model(model_id: str, cache_dir: str):
    """
    Downloads a Hugging Face model and stores it in the specified cache directory.

    Args:
        model_id (str): The identifier of the model to download from Hugging Face.
        cache_dir (str): The directory where the model should be cached.

    Returns:
        None

    Logs:
        Logs the start and completion of the model download process, including the path where the model is stored.
    """

    logger.info(f"Starting {model_id} model download...")

    model_path = snapshot_download(repo_id=model_id, cache_dir=cache_dir)

    logger.info(f"Repository downloaded to: {model_path}")


def convert_model(model_id: str, cache_dir: str, model_type: str):
    """
    Converts a specified model to OpenVINO format and saves it to the cache directory.

    Args:
        model_id (str): The identifier of the model to be converted.
        cache_dir (str): The directory where the converted model will be saved.
        model_type (str): The type of the model. It can be "embedding", "reranker", or "llm".

    Returns:
        None

    Raises:
        ValueError: If the model_type is not one of "embedding", "reranker", or "llm".

    Notes:
        - If the model has already been converted and exists in the cache directory, the conversion process is skipped.
        - The function uses the Hugging Face `AutoTokenizer` to load and save the tokenizer.
        - The function uses OpenVINO's `convert_tokenizer` and `save_model` to convert and save the tokenizer.
        - Depending on the model_type, the function uses different OpenVINO model classes to convert and save the model.
    """

    if os.path.isdir(cache_dir + "/" + model_id):
        logger.info(f"Optimized {model_id} exist in {cache_dir}. Skip process...")
    else:
        logger.info(f"Converting {model_id} model to OpenVINO format...")
        hf_tokenizer = AutoTokenizer.from_pretrained(model_id)
        hf_tokenizer.save_pretrained(f"{cache_dir}/{model_id}")
        ov_tokenizer = convert_tokenizer(hf_tokenizer, add_special_tokens=False)
        ov.save_model(ov_tokenizer, f"{cache_dir}/{model_id}/openvino_tokenizer.xml")

        if model_type == "embedding":
            embedding_model = OVModelForFeatureExtraction.from_pretrained(
                model_id, export=True
            )
            embedding_model.save_pretrained(f"{cache_dir}/{model_id}")
        elif model_type == "reranker":
            reranker_model = OVModelForSequenceClassification.from_pretrained(
                model_id, export=True
            )
            reranker_model.save_pretrained(f"{cache_dir}/{model_id}")
        elif model_type == "llm":
            llm_model = OVModelForCausalLM.from_pretrained(
                model_id, export=True, weight_format="int8"
            )
            llm_model.save_pretrained(f"{cache_dir}/{model_id}")


def get_available_devices():
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
    supported_properties = core.get_property(device, "SUPPORTED_PROPERTIES")

    for property_key in supported_properties:
        if property_key not in ('SUPPORTED_METRICS', 'SUPPORTED_CONFIG_KEYS', 'SUPPORTED_PROPERTIES'):
            try:
                property_val = core.get_property(device, property_key)

                # Convert non-serializable types to strings
                if not isinstance(property_val, (str, int, float, bool, type(None))):
                    property_val = str(property_val)

            except TypeError:
                property_val = "UNSUPPORTED TYPE"

            properties_dict[property_key] = property_val

    return properties_dict
