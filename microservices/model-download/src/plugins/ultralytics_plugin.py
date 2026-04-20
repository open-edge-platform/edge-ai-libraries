# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.utils.logging import logger

class UltralyticsDownloader(ModelDownloadPlugin):
    """Plugin for downloading Ultralytics models"""
    
    _script_lock = threading.Lock()

    @property
    def plugin_name(self) -> str:
        return "ultralytics"
    
    @property
    def plugin_type(self) -> str:
        return "downloader"
    
    def can_handle(self, model_name: str, hub: str, **kwargs) -> bool:
        """Check if this plugin can handle the given model"""
        # Case-insensitive check for the hub name
        if hub.lower() == "ultralytics":
            return True
        
        # Check if the model is in the list of supported models
        try:
            supported_models = self.get_supported_models()
            #model_without_prefix = model_name.split(":")[-1] if ":" in model_name else model_name
            return model_name in supported_models or model_name == "all"
        except:
            return False

    def download(self, model_name: str, output_dir: str, **kwargs) -> Dict[str, Any]:
        """Download the model using the bash script"""
        # Remove prefix if present
        #model_without_prefix = model_name.split(":")[-1] if ":" in model_name else model_name
        
        # Extract quantization from kwargs
        quantize = (kwargs.get("config") or {}).get("quantize") or ""
        quantize = quantize.strip()
        int8_requested = bool(quantize)

        # Validate: INT8 quantization requires single model (not comma-separated, all, or yolo_all)
        if int8_requested:
            is_multi_model_in_request = "," in model_name or model_name in ("all", "yolo_all")
            if is_multi_model_in_request:
                raise ValueError(
                    f"INT8 requires a single model. Received '{model_name}' with quantize='{quantize}'. "
                    "Use a single model and retry (e.g., 'yolov8n' instead of 'comma-separated-models', 'all', or 'yolo_all')."
                )
        
        # Create hub-specific directory under the output directory
        hub_dir = os.path.join(output_dir, "ultralytics")
        
        # Call the download script
        with self._script_lock:
            return_code = self._call_bash_script(model=model_name, quantize=quantize, models_path=hub_dir)

        if int8_requested and return_code == 0:
            int8_artifacts = self._find_int8_artifacts(hub_dir, model_name)
            if not int8_artifacts:
                self._cleanup_requested_model_artifacts(hub_dir, model_name)
                raise RuntimeError(
                    f"INT8 export not supported for '{model_name}' (dataset='{quantize}'). "
                    "No INT8 artifacts were generated."
                )

        if return_code != 0:
            if int8_requested:
                self._cleanup_requested_model_artifacts(hub_dir, model_name)
                raise RuntimeError(
                    f"INT8 download attempt failed for Ultralytics model '{model_name}' using dataset '{quantize}' "
                    f"(script exit code: {return_code}).Check whether this model supports INT8 export, or retry without quantize."
                )
            raise RuntimeError(f"Failed to download Ultralytics model {model_name}. Check if the model name is correct and if the model is compatible")
        
        host_path = hub_dir
        if host_path and isinstance(host_path, str) and host_path.startswith("/opt/models/"):
            host_prefix = os.getenv("MODEL_PATH", "models")
            host_path = host_path.replace("/opt/models/", f"{host_prefix}/")
        
        return {
            "model_name": model_name,
            "source": "ultralytics",
            "download_path": host_path,
            "int8_requested": int8_requested,
            "success": True
        }

    def _cleanup_requested_model_artifacts(self, hub_dir: str, model_name: str) -> None:
        """Remove downloaded artifacts for a single model after strict INT8 failure."""
        public_dir = Path(hub_dir) / "public"
        if not public_dir.exists():
            return

        for candidate in {model_name, Path(model_name).stem}:
            shutil.rmtree(public_dir / candidate, ignore_errors=True)

    def _find_int8_artifacts(self, hub_dir: str, model_name: str) -> List[str]:
        """Find INT8 XML artifacts produced by the download script."""
        public_dir = Path(hub_dir) / "public"
        if not public_dir.exists():
            return []

        # Some exports keep the model extension in folder name, others use stem only.
        primary_dir = public_dir / model_name / "INT8"
        int8_xml_path = next(primary_dir.glob("*.xml"), None)

        if not int8_xml_path:
            fallback_dir = public_dir / Path(model_name).stem / "INT8"
            int8_xml_path = next(fallback_dir.glob("*.xml"), None)

        # Return one INT8 XML path if found in either directories; otherwise empty list.
        return [str(int8_xml_path)] if int8_xml_path else []
    
    def get_supported_models(self) -> List[str]:
        """Get list of supported models from the bash script"""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "download_public_models.sh"
        
        if not script_path.exists():
            raise FileNotFoundError(f"Bash script not found at {script_path}")
            
        with open(script_path, 'r') as f:
            script_content = f.read()
        
        # Extract SUPPORTED_MODELS section
        start = script_content.find("SUPPORTED_MODELS=(")
        end = script_content.find(")", start)
        models_section = script_content[start:end]
        
        # Parse models
        models = []
        for line in models_section.split('\n'):
            line = line.strip()
            if line.startswith('"') and line.endswith('"'):
                models.append(line.strip('"'))
        
        return models
    
    def get_supported_quantization_datasets(self) -> Dict[str, str]:
        """Get dict of supported quantization datasets from the bash script"""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "download_public_models.sh"
        
        if not script_path.exists():
            raise FileNotFoundError(f"Bash script not found at {script_path}")
            
        with open(script_path, 'r') as f:
            script_content = f.read()
        
        # Extract SUPPORTED_QUANTIZATION_DATASETS section
        start = script_content.find("SUPPORTED_QUANTIZATION_DATASETS=(")
        end = script_content.find(")", start)
        datasets_section = script_content[start:end]
        
        # Parse datasets
        datasets = {}
        for line in datasets_section.split('\n'):
            line = line.strip()
            if '[' in line and ']=' in line:
                parts = line.split(']=')
                key = parts[0].strip('[" ')
                value = parts[1].strip(' "')
                if key and value:
                    datasets[key] = value
        
        return datasets
    
    def _call_bash_script(self, model: str = "all", quantize: str = "", models_path: str = "") -> int:
        """Call the download_public_models.sh bash script with arguments"""
        # Find script path relative to this file
        script_path = str(Path(__file__).parent.parent.parent / "scripts" / "download_public_models.sh")

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Bash script not found at {script_path}")

        cmd = ["bash", str(script_path), model]
        if quantize:
            cmd.append(quantize)

        logger.info(f"Executing: {' '.join(cmd)}")

        # Prepare environment with MODELS_PATH
        env = os.environ.copy()
        env['MODELS_PATH'] = models_path
        logger.info(f"Setting MODELS_PATH to {models_path}")
        # Execute the bash script and capture output
        logger.info(f"Starting download for Ultralytics model: {env}")    
        logger.info("Command to be executed: " + ' '.join(cmd))
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            text=True,
            env=env
        )
        
        # Stream output in real-time
        while True:
            stdout_line = process.stdout.readline() if process.stdout else ""
            stderr_line = process.stderr.readline() if process.stderr else ""
            
            if stdout_line:
                logger.info(stdout_line.strip())
            if stderr_line:
                logger.error(stderr_line.strip())
                
            if not stdout_line and not stderr_line and process.poll() is not None:
                break
        
        return_code = process.poll()
        if return_code is None:
            return_code = 0  # If process is still running, assume success
        if return_code != 0:
            logger.error(f"Script execution failed with return code {return_code}")

        return return_code
        
    def download_task(self, task: DownloadTask, output_dir: str, **kwargs) -> str:
        """
        Download a specific file for Ultralytics models.
        Note: This method is required for parallel downloading but Ultralytics typically uses
        a single script download rather than per-file downloads.
        """
        raise NotImplementedError("Ultralytics plugin does not support individual file downloads")
    
    async def post_process(self, model_name: str, output_dir: str, downloaded_paths: List[str], **kwargs) -> Dict[str, Any]:
        """
        Post-process the downloaded files.
        For Ultralytics, this is usually handled by the download script directly.
        """
        return {
            "model_name": model_name,
            "source": "ultralytics",
            "download_path": output_dir,
            "success": True
        }