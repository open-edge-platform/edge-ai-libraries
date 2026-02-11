# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
from collections import deque
from typing import Dict, Any, Optional, List
from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.utils.logging import logger


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

    def convert(self, model_name: str, output_dir: str, hf_token: str, **kwargs) -> Dict[str, Any]:
        """
        Convert a model to OpenVINO Model Server (OVMS) format.
        This is the main conversion method expected by the model manager.
        """
        # Extract parameters from the new payload structure
        # Handle both direct parameters and nested config
        config = kwargs.get("config", {})
        logger.info(f"Payload {model_name}, {output_dir}, {kwargs}")
        logger.info(f"Conversion config: {kwargs.get('config', {})}")
        # Extract parameters with fallbacks to maintain backward compatibility
        weight_format = config.get("precision", kwargs.get("precision")) or "int8"
        huggingface_token = hf_token
        model_type = kwargs.get("type", kwargs.get("model_type", "llm"))
        version = kwargs.get("version", "")
        target_device = config.get("device", kwargs.get("device")) or "CPU"
        cache_size = config.get("cache", kwargs.get("cache_size"))

        if target_device.upper() == "NPU":
            logger.warning("NPU target device selected. Only 'int4' weight format is supported for NPU. Overriding weight_format to 'int4'.")
            weight_format = "int4"
            if model_type != "llm" and model_type != "vlm":
                raise RuntimeError("NPU target device is only supported for 'llm' and 'vlm' model types.")
            if output_dir.endswith("/fp16") or output_dir.endswith("/int8") or output_dir.endswith("/int4"):
                output_dir = output_dir.rsplit("/", 1)[0] + "/int4"
        
        try:
            # Perform the conversion
            result = self.convert_to_ovms_format(
                weight_format=weight_format,
                huggingface_token=huggingface_token,
                model_type=model_type,
                target_device=target_device,
                model_directory=output_dir,
                cache_size=cache_size,
                version=version,
                model_name=model_name 
            )

            host_path = output_dir
            if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
                host_prefix = os.getenv("MODEL_PATH", "models")
                host_path = host_path.replace("/opt/models/", f"{host_prefix}/")
            #Check the result of conversion
            if result["returncode"] != 0:
                raise RuntimeError(f"Model conversion failed due to {result['stderr']}! Also, Check if the model is compatible to be converted with Openvino and the configuration provided. ")
            
            return {
                "model_name": model_name,
                "source": "openvino",
                "type": model_type,
                "conversion_path": host_path,
                "is_ovms": True,
                "config": {
                    "precision": weight_format,
                    "device": target_device,
                    "cache": cache_size if cache_size is not None else None
                },
                "success": True,
                "message": "Model successfully converted to OVMS format."
            }
        except Exception as e:
            logger.error(f"Failed to convert model to OVMS format: {str(e)}")
            raise RuntimeError(f"Failed to convert model to OVMS format: {str(e)}")
            
    def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
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
        cache_size: Optional[int] = None,
    ):
        """
        Convert a downloaded model to OpenVINO Model Server (OVMS) format.

        Args:
            model_name (str): The name of the Hugging Face model to download.
            weight_format (str): The weight format for the exported model (e.g., "int4", "fp16").
            huggingface_token (str): The Hugging Face API token for authentication.
            model_type (str): The type of the model (e.g., "llm", "embeddings", "rerank").
            target_device (str): Target hardware device for optimization (e.g., "CPU", "GPU", "NPU").
            model_directory (str): Directory to save the converted model.
            cache_size (int, optional): Cache size for model optimization.

        Raises:
            RuntimeError: If model type is invalid, authentication fails, or model conversion fails
        """
        # Map model_type to export type
        export_type_map = {
            "llm": "text_generation",
            "embeddings": "embeddings_ov",
            "rerank": "rerank_ov",
            "vlm": "vlm",
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

        logger.info("Checking for export_model.py script...")
        # THIS IS COMMENTED FOR FUTURE UPDATES
        # export_script_url = "https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/4/demos/common/export_models/export_model.py"
      
        # if not os.path.exists("export_model.py"):
        #     logger.info(f"Downloading export_model.py script...")
        #     try:
        #         subprocess.run(["curl", export_script_url, "-o", "export_model.py"], check=True)
        #     except subprocess.CalledProcessError as e:
        #         raise RuntimeError(f"Failed to download export script: {str(e)}")
        # else:
        #     logger.info("export_model.py already exists, skipping download.")

        # Step 4: Export the model using the virtual environment's Python
        logger.info(f"Exporting model: {model_name} with weight format: {weight_format} and export type: {export_type}...")

        # Ensure models directory exists
        os.makedirs(model_directory, exist_ok=True)
        
        if model_type == "vlm":
            command = [
                "python3", "scripts/export_model.py", "text_generation",
                "--source_model", model_name,
                "--weight-format", weight_format,
                "--pipeline_type", "VLM",
                "--config_file_path", f"{model_directory}/config.json",
                "--model_repository_path", f"{model_directory}/",
                "--target_device", target_device
            ]
        else:    
            # Build command with Python from the virtual environment
            command = [
                "python3", "scripts/export_model.py", export_type,
                "--source_model", model_name,
                "--weight-format", weight_format,
                "--config_file_path", f"{model_directory}/config.json",
                "--model_repository_path", f"{model_directory}/",
                "--target_device", target_device
            ]

            if version:
                command += ["--version", version]
            if export_type == "text_generation" and cache_size is not None:
                command += ["--cache_size", f"{cache_size}"]

        logger.info(f"Executing command with virtual environment: {command}")
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
        weight_format = config.get("precision", kwargs.get("precision", "int8"))
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
