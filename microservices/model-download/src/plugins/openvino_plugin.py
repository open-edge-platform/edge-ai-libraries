# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
from collections import deque
from enum import Enum
from typing import Dict, Any, Optional, List
from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.api.models import OPENVINO_EXPORT_PARAMS, EXPORT_TYPE_PARAMS
from src.utils.logging import logger

# Default OVMS release tag for export_model.py script
OVMS_RELEASE_TAG = os.getenv("OVMS_RELEASE_TAG", "v2025.4.1")


class OpenVINOConverter(ModelDownloadPlugin):
    """
    Plugin for converting models to OpenVINO format for deployment with OpenVINO Model Server (OVMS).
    Supports converting models from various sources to optimized OpenVINO IR format.
    """

    @property
    def plugin_name(self) -> str:
        return "openvino"

    @property
    def plugin_type(self) -> str:
        return "converter"  # This is a converter plugin, not a downloader

    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        # Check if the hub is openvino or if is_ovms is True
        return hub.lower() == "openvino" or kwargs.get("is_ovms", False)
    
    def _get_param(self, param_name: str, config: Dict[str, Any], kwargs: Dict[str, Any], default_value: Any = None) -> Any:
        """
        Extract parameter with fallback chain.
        
        Priority:
        1. Config level
        2. Direct kwargs
        3. Default value
        
        Args:
            param_name: Parameter name to extract
            config: Config dictionary
            kwargs: Direct kwargs passed to method
            default_value: Fallback default value
            
        Returns:
            Parameter value or default_value if not found
        """
        # Check config level first
        if isinstance(config, dict) and param_name in config:
            return config[param_name]
        
        # Fall back to direct kwargs
        if param_name in kwargs:
            return kwargs[param_name]
        
        return default_value

    def _convert_value_to_string(self, value: Any) -> str:
        """
        Convert any value to string, handling Enum types properly.
        
        Args:
            value: Value to convert
            
        Returns:
            String representation of the value
        """
        if isinstance(value, Enum):
            return value.value
        return str(value)

    def _build_export_command(
        self,
        export_type: str,
        model_name: str,
        output_dir: str,
        config_dict: Optional[Dict[str, Any]] = None,
        target_device: str = "CPU",
        weight_format: str = "int8"
    ) -> List[str]:
        """
        Build export_model.py command         
        Args:
            export_type: Model type (text_generation, embeddings_ov, rerank_ov)
            model_name: Source model identifier
            output_dir: Output directory path
            config_dict: Configuration dictionary (can contain any parameters)
            target_device: Target device (CPU, GPU, NPU, HETERO)
            weight_format: Precision format (int4, int8, fp16, fp32)
            
        Returns:
            List of command arguments ready for subprocess execution
        """
        config_dict = config_dict or {}
        
        # Convert enum values to strings in base parameters
        weight_format_str = self._convert_value_to_string(weight_format)
        target_device_str = self._convert_value_to_string(target_device)
        
        # Base command
        command = [
            "python3", "scripts/export_model.py", export_type,
            "--source_model", model_name,
            "--weight-format", weight_format_str,
            "--config_file_path", f"{output_dir}/config_all.json",
            "--model_repository_path", f"{output_dir}/",
            "--target_device", target_device_str
        ]
        
        logger.info(f"The additional params are {config_dict}")
        # Process all parameters
        for param_name, param_value in config_dict.items():
            if param_value is None:
                continue  # Skip None values

            # Skip parameters that are already handled as base command arguments or metadata
            if param_name in ("precision", "device", "source_model", "type", "model_type"):
                continue

            if param_name in OPENVINO_EXPORT_PARAMS:
                # Use documented mapping for known parameters
                flag_name, param_type = OPENVINO_EXPORT_PARAMS[param_name]

                if param_type == "bool":
                    if param_value:  # Only add flag if True
                        command.append(flag_name)
                        logger.debug(f"Added parameter: {flag_name} (bool)")
                else:
                    # For string/int types, always add flag and value
                    command.append(flag_name)
                    param_value_str = self._convert_value_to_string(param_value)
                    # Strip any existing quotes first
                    param_value_str = param_value_str.strip('"')
                    # Add quotes around the value if it contains spaces (needed for script parsing)
                    if " " in param_value_str:
                        param_value_str = f"{param_value_str}"
                    command.append(param_value_str)
                    logger.debug(f"Added parameter: {flag_name} {param_value_str}")
            else:
                flag_name = "--" + param_name  #.replace("_", "-")

                logger.info(f"Parameter '{param_name}' not in known_params mapping. "
                           f"Passing to export_model.py as: {flag_name}={param_value}")

                if isinstance(param_value, bool):
                    if param_value:
                        command.append(flag_name)
                else:
                    command.append(flag_name)
                    param_value_str = self._convert_value_to_string(param_value)
                    # Strip any existing quotes first
                    param_value_str = param_value_str.strip('"')
                    # Add quotes around the value if it contains spaces (needed for script parsing)
                    if " " in param_value_str:
                        param_value_str = f'"{param_value_str}"'
                    command.append(param_value_str)
        
        return command

    def convert(self, model_name: str, output_dir: str, hf_token: str, **kwargs) -> Dict[str, Any]:
        """
        Convert a model to OpenVINO Model Server (OVMS) format.
        This is the main conversion method expected by the model manager.
        """        
        # Extract core parameters using helper (supports multiple sources)
        weight_format = kwargs.get("precision",kwargs.get("weight-format"))
        target_device = kwargs.get("device",kwargs.get("target_device"))
        cache_size = kwargs.get("cache_size", kwargs.get("cache", None))
        
        # Extract model metadata
        huggingface_token = hf_token
        model_type = kwargs.get("type", kwargs.get("model_type", "llm"))
        version = kwargs.get("version", "")
        
        # Always use flat config structure for export, passthrough all config params
        config_for_export = kwargs.copy()
        config_for_export.pop("weight-format", None)
        config_for_export.pop("target_device", None)
        logger.info(f"Using flat config structure: {list(config_for_export.keys())}")
        logger.info(f"Extracted parameters - precision: {weight_format}, device: {target_device}, cache_size: {cache_size}")
        
        # Handle NPU special cases
        if str(target_device).upper() == "NPU":
            logger.warning("NPU target device selected. Only 'int4' weight format is supported for NPU. Overriding weight_format to 'int4'.")
            weight_format = "int4"
            config_for_export["precision"] = "int4"
            if model_type != "llm" and model_type != "vlm":
                raise RuntimeError("NPU target device is only supported for 'llm' and 'vlm' model types.")
            if output_dir.endswith("/fp16") or output_dir.endswith("/int8") or output_dir.endswith("/int4"):
                output_dir = output_dir.rsplit("/", 1)[0] + "/int4"
        
        try:
            # Perform the conversion
            result = self.convert_to_ovms_format(
                model_name=model_name,
                weight_format=weight_format,
                huggingface_token=huggingface_token,
                model_type=model_type,
                target_device=target_device,
                model_directory=output_dir,
                version=version,
                config_dict=config_for_export
            )

            host_path = output_dir
            if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
                host_prefix = os.getenv("MODEL_PATH", "models")
                host_path = host_path.replace("/opt/models/", f"{host_prefix}/")
            
            # Check the result of conversion
            if result["returncode"] != 0:
                raise RuntimeError(f"Model conversion failed due to {result['stderr']}! Also, check if the model is compatible to be converted with OpenVINO and the configuration provided.")
            
            # Build response config - only include parameters that were in the original request
            response_config = {}
            if isinstance(kwargs, dict):
                if "precision" in kwargs:
                    response_config["precision"] = weight_format
                if "device" in kwargs:
                    response_config["device"] = target_device
                if ("cache_size" in kwargs or "cache" in kwargs) and cache_size is not None:
                    response_config["cache"] = cache_size
            
            return {
                "model_name": model_name,
                "source": "openvino",
                "type": model_type,
                "conversion_path": host_path,
                "is_ovms": True,
                "config": response_config,
                "success": True,
                "message": "Model successfully converted to OVMS format."
            }
        except Exception as e:
            logger.error(f"Failed to convert model to OVMS format: {str(e)}")
            raise RuntimeError(f"Failed to convert model to OVMS format: {str(e)}")
            
    async def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        """
        This plugin is a converter, not a downloader, but implementing this method for compatibility.
        Raises NotImplementedError as this plugin does not support direct downloads.
        """
        raise NotImplementedError("OpenVINO plugin is a converter, not a downloader. Use the convert method instead.")

    def convert_to_ovms_format(
        self,
        model_name: str,
        weight_format: str,
        huggingface_token: Optional[str],
        model_type: str,
        target_device: str,
        model_directory: str,
        version: str = "",
        config_dict: Optional[Dict[str, Any]] = None,
    ):
        """
        Convert a downloaded model to OpenVINO Model Server (OVMS) format using export_model.py.
        Supports all export_model.py arguments via config_dict parameters.

        Args:
            model_name (str): The name of the Hugging Face model to download.
            weight_format (str): The weight format for the exported model (e.g., "int4", "fp16").
            huggingface_token (str): The Hugging Face API token for authentication.
            model_type (str): The type of the model (e.g., "llm", "embeddings", "rerank", "vlm").
            target_device (str): Target hardware device for optimization (e.g., "CPU", "GPU", "NPU").
            model_directory (str): Directory to save the converted model.
            cache_size (int, optional): Cache size for model optimization.

        Raises:
            RuntimeError: If model type is invalid, authentication fails, or model conversion fails
        """
        config_dict = config_dict or {}
        
        # Map model_type to export type
        export_type_map = {
            "llm": "text_generation",
            "text_generation": "text_generation",
            "embeddings_ov": "embeddings_ov",
            "rerank_ov": "rerank_ov",
            "embeddings": "embeddings_ov",
            "rerank": "rerank_ov",
            "vlm": "text_generation",  # VLM uses text_generation type
            "image_generation": "image_generation",
            "text2speech": "text2speech",
            "speech2text": "speech2text"
        }

        # Validate model_type
        if model_type not in export_type_map:
            raise RuntimeError(
                f"Invalid model_type: {model_type}. Must be one of {list(export_type_map.keys())}."
            )

        export_type = export_type_map[model_type]

        # Validate that HF token is provided for OVMS conversion
        if not huggingface_token:
            raise RuntimeError(
                "Hugging Face token is required for OVMS conversion"
            )

        # Step 1: Log in to Hugging Face,
        logger.info(f"Logging in to Hugging Face with token...")
        check_login = subprocess.run(
            ["hf", "auth", "whoami"],
            capture_output=True,
            text=True
        )
        
        if check_login.returncode != 0:
            # Not logged in, proceed with login
            logger.info("Not logged in, authenticating with Hugging Face...")
            result = subprocess.run(["hf", "auth", "login", "--token", huggingface_token])
            if result.returncode != 0:
                raise RuntimeError(
                    "Failed to authenticate with Hugging Face. Please check your token."
                )
        else:
            logger.info(f"Already logged in to Hugging Face as: {check_login.stdout.strip()}")

        # Export the model using export_model.py with intelligent parameter handling
        logger.info(f"Exporting model: {model_name} with weight format: {weight_format} and export type: {export_type}...")

        # Ensure models directory exists
        os.makedirs(model_directory, exist_ok=True)
        
        # Add VLM-specific parameter if needed
        if model_type == "vlm" and "pipeline_type" not in config_dict:
            config_dict["pipeline_type"] = "VLM"
        if model_type == "embeddings" or model_type == "rerank":
            config_dict.pop("cache_size", None)  

        logger.info(f"Final parameters to be passed to export_model.py: {config_dict}")
        # Build command using smart parameter builder
        command = self._build_export_command(
            export_type=export_type,
            model_name=model_name,
            output_dir=model_directory,
            config_dict=config_dict,
            target_device=target_device,
            weight_format=weight_format
        )
        
        # Add version if specified
        if version:
            command.extend(["--version", version])

        logger.info(f"Executing export_model.py command: {' '.join(command)}")
        try:
            result = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                text=True
            )
            stderr_logs = deque(maxlen=3)
            stdout_logs = deque(maxlen=3)
            # Stream output in real-time
            while True:
                stdout_line = result.stdout.readline() if result.stdout else ""
                stderr_line = result.stderr.readline() if result.stderr else ""

                if stdout_line:
                    stdout_logs.append(stdout_line.strip())
                    logger.info(stdout_logs[-1])
                if stderr_line:
                    stderr_logs.append(stderr_line.strip())
                    logger.error(stderr_logs[-1])
                if not stdout_line and not stderr_line and result.poll() is not None:
                    break
            return_code = result.poll()
            if return_code is None:
                return_code = 0  # If process is still running, assume success
            if return_code != 0:
                #If model_type is vlm and the conversion fails, use the direct PyTorch to OpenVINO converter as fallback
                if model_type == "vlm":
                    logger.info("VLM model conversion failed with export_model.py, attempting fallback conversion using direct PyTorch to OpenVINO converter...")
                    command = [
                        "python3", "scripts/convert_model_vlm.py", 
                        "--model-name", model_name,
                        "--download-path", model_directory,
                        "--precision", weight_format,
                        "--device", target_device.lower()
                    ]                    
                    logger.info(f"Executing fallback command: {' '.join(command)}")
                    result = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, text=True)

                    # Stream output in real-time
                    while True:
                        stdout_line = result.stdout.readline() if result.stdout else ""
                        stderr_line = result.stderr.readline() if result.stderr else ""

                        if stdout_line:
                            stdout_logs.append(stdout_line.strip())
                            logger.info(stdout_line.strip())
                        if stderr_line:
                            stderr_logs.append(stderr_line.strip())
                            logger.error(stderr_line.strip())

                        if not stdout_line and not stderr_line and result.poll() is not None:
                            break
                    return_code = result.poll()
                    
                    if result.returncode != 0:
                        last_error = list(stderr_logs)[-1] if len(stderr_logs) > 0 else "Unknown error"
                        last_output = list(stdout_logs)[-1] if len(stdout_logs) > 0 else ""
                        logger.error(f"Fallback VLM conversion failed: {last_error}")
                        if last_output:
                            logger.error(f"Fallback stdout: {last_output}")
                        return_code = result.returncode
                    else:
                        logger.info("Fallback VLM conversion succeeded.")
                        last_output = list(stdout_logs)[-1] if len(stdout_logs) > 0 else ""
                        if last_output:
                            logger.info(f"Conversion output: {last_output}")
                        return_code = 0
                else:
                    last_error = list(stderr_logs)[-1] if len(stderr_logs) > 0 else "Unknown error"
                    logger.error(f"Script execution failed with return code {last_error}")
        
            final_output = {
                "stdout": list(stdout_logs)[-1] if len(stdout_logs) > 0 else "",
                "stderr": list(stderr_logs)[-1] if len(stderr_logs) > 0 else "",
                "returncode": return_code
            }

            return final_output
           
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Model conversion failed: {str(e)}. Check if the model is compatible with the specified format and device."
            )

    def get_download_tasks(self, model_name: str, **kwargs) -> List[DownloadTask]:
        """
        Get list of download tasks for a model.
        OpenVINO converter does not support task-based downloading.
        """
        raise NotImplementedError("OpenVINO converter does not support task-based downloading")
    
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """
        Download a single task file.
        OpenVINO converter does not support task-based downloading.
        """
        raise NotImplementedError("OpenVINO converter does not support task-based downloading")
    
    async def post_process(self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        Post-process the converted files.
        For OpenVINO conversion, this is handled by the download/convert method directly.
        """
        # Extract parameters to maintain consistent response structure
        config = kwargs.get("config", {})
        weight_format = config.get("precision", kwargs.get("weight-format", "int8"))
        model_type = kwargs.get("type", kwargs.get("model_type", "llm"))
        target_device = config.get("device", kwargs.get("target_device", "CPU"))
        cache_size = config.get("cache", kwargs.get("cache_size"))
        
        return {
            "model_name": model_name,
            "source": "openvino",
            "type": model_type,
            "conversion_path": output_dir,
            "is_ovms": True,
            "config": {
                "precision": weight_format,
                "device": target_device,
                "cache": cache_size if cache_size is not None else None
            },
            "success": True,
            "message": "Model conversion completed successfully."
        }
