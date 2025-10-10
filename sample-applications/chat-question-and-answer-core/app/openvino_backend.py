from .config import config
from .logger import logger
from huggingface_hub import login, whoami, snapshot_download
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
from optimum.intel import (
    OVModelForFeatureExtraction,
    OVModelForSequenceClassification,
    OVModelForCausalLM,
)
from transformers import AutoTokenizer
from openvino_tokenizers import convert_tokenizer
from langchain_community.embeddings import OpenVINOBgeEmbeddings
from langchain_community.document_compressors.openvino_rerank import OpenVINOReranker
from langchain_huggingface import HuggingFacePipeline
import os
import openvino as ov


class OpenVINOBackend:
    def __init__(self):
        self.huggingface_token = config.HF_ACCESS_TOKEN
        self.cache_dir = config._CACHE_DIR
        self.embedding_model_id = config.EMBEDDING_MODEL_ID
        self.llm_model_id = config.LLM_MODEL_ID
        self.reranker_model_id = config.RERANKER_MODEL_ID
        self.embedding_device = config.EMBEDDING_DEVICE
        self.reranker_device = config.RERANKER_DEVICE
        self.llm_device = config.LLM_DEVICE
        self.max_tokens = config.MAX_TOKENS

    def login_to_huggingface(self, token: str):
        """
        Logs in to Hugging Face using the provided token and checks the authenticated user.

        Args:
            token (str): The authentication token for Hugging Face.

        Returns:
            None
        """

        try:
            logger.info("Logging in to Hugging Face...")
            login(token=token)
            user_info = whoami()

            if user_info:
                logger.info(f"Logged in successfully as {user_info['name']}")
            else:
                logger.error("Login failed.")
                raise RuntimeError("Login to Hugging Face failed. Please check your token.")

        except HfHubHTTPError as e:
            logger.error(f"Login failed due to Hugging Face Hub error: {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error during Hugging Face login: {e}")
            raise

    def download_huggingface_model(self, model_id: str, cache_dir: str):
        """
        Downloads a model from the Hugging Face Hub and caches it locally.

        Args:
            model_id (str): The identifier of the model repository on Hugging Face Hub.
            cache_dir (str): The directory path where the model should be cached.

        Raises:
            RepositoryNotFoundError: If the specified model repository does not exist.
            HfHubHTTPError: If an HTTP error occurs while accessing the Hugging Face Hub.
            Exception: For any other unexpected errors during the download process.

        Logs:
            Information about the download process, including start, completion, and any errors encountered.
        """

        try:
            logger.info(f"Downloading model {model_id} from HuggingFace Hub...")

            # 'main' is the only available revision and already handled in snapshot_download module
            model_path = snapshot_download(repo_id=model_id, cache_dir=cache_dir)  # nosec B615

            logger.info(f"Model downloaded successfully to {model_path}")

        except RepositoryNotFoundError as e:
            logger.error(f"Model repository not found: {model_id}")
            raise

        except HfHubHTTPError as e:
            logger.error(f"Hugging Face Hub HTTP error: {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error downloading model '{model_id}': {e}")
            raise

    def convert_model(self, model_id: str, cache_dir: str, model_type: str):
        """
        Converts a specified model to OpenVINO™ toolkit format and saves it to the cache directory.

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
            - The function uses OpenVINO toolkit's `convert_tokenizer` and `save_model` to convert and save the tokenizer.
            - Depending on the model_type, the function uses different OpenVINO model classes to convert and save the model.
        """

        model_path = os.path.join(cache_dir, model_id)

        if os.path.isdir(model_path):
            logger.info(f"Optimized {model_id} exists in {cache_dir}. Skipping conversion...")
            return

        logger.info(f"Converting {model_id} model to OpenVINO™ toolkit format...")
        # 'main' is the only available revision and already handled in huggingfacehub module
        hf_tokenizer = AutoTokenizer.from_pretrained(model_id)  # nosec B615
        hf_tokenizer.save_pretrained(model_path)
        ov_tokenizer = convert_tokenizer(hf_tokenizer, add_special_tokens=False)
        ov.save_model(ov_tokenizer, f"{model_path}/openvino_tokenizer.xml")

        if model_type == "embedding":
            model = OVModelForFeatureExtraction.from_pretrained(
                model_id,
                export=True,
                trust_remote_code=True
            )

        elif model_type == "reranker":
            model = OVModelForSequenceClassification.from_pretrained(
                model_id,
                export=True,
                trust_remote_code=True
            )

        elif model_type == "llm":
            model = OVModelForCausalLM.from_pretrained(
                model_id,
                export=True,
                weight_format="int8",
                trust_remote_code=True
            )

        else:
            raise ValueError(
                f"Unsupported model type: {model_type}. Supported types are 'embedding', 'reranker', and 'llm'."
            )

        model.save_pretrained(model_path)

    def init_models(self):
        """
        Initializes the OpenVINO models for embedding, LLM, and reranking.

        Returns:
            tuple: A tuple containing the initialized embedding model, LLM model, and reranker model.
        """

        # Login to HuggingFace
        self.login_to_huggingface(self.huggingface_token)

        # Download embedding, LLM, and reranker models from HuggingFace
        self.download_huggingface_model(self.embedding_model_id, self.cache_dir)
        self.download_huggingface_model(self.reranker_model_id, self.cache_dir)
        self.download_huggingface_model(self.llm_model_id, self.cache_dir)

        # Convert models
        self.convert_model(self.embedding_model_id, self.cache_dir, "embedding")
        self.convert_model(self.reranker_model_id, self.cache_dir, "reranker")
        self.convert_model(self.llm_model_id, self.cache_dir, "llm")

        # Initialize embedding model
        embedding = OpenVINOBgeEmbeddings(
            model_name_or_path = os.path.join(self.cache_dir, self.embedding_model_id),
            model_kwargs = {"device": self.embedding_device, "compile": False},
        )
        embedding.ov_model.compile()

        # Initialize reranker model
        reranker = OpenVINOReranker(
            model_name_or_path = os.path.join(self.cache_dir, self.reranker_model_id),
            model_kwargs = {"device": self.reranker_device},
            top_n = 2,
        )

        # Initialize LLM
        llm = HuggingFacePipeline.from_model_id(
            model_id = os.path.join(self.cache_dir, self.llm_model_id),
            task = "text-generation",
            backend = "openvino",
            model_kwargs = {
                "device": self.llm_device,
                "ov_config": {
                    "PERFORMANCE_HINT": "LATENCY",
                    "NUM_STREAMS": "1",
                    "CACHE_DIR": os.path.join(self.cache_dir, self.llm_model_id, "model_cache"),
                },
                "trust_remote_code": True,
            },
            pipeline_kwargs = {"max_new_tokens": self.max_tokens},
        )

        if llm.pipeline.tokenizer.eos_token_id:
            llm.pipeline.tokenizer.pad_token_id = llm.pipeline.tokenizer.eos_token_id

        return embedding, llm, reranker

    @staticmethod
    def get_available_devices():
        """
        Retrieves a list of available devices from the OpenVINO core.

        Returns:
            list: A list of available device names.
        """

        core = ov.Core()
        device_list = core.available_devices

        return device_list

    @staticmethod
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
