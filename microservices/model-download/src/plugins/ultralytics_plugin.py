import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

from src.core.interfaces import ModelDownloadPlugin, DownloadTask
from src.utils.logging import logger

class UltralyticsDownloader(ModelDownloadPlugin):
    """Plugin for downloading Ultralytics models"""
    
    @property
    def plugin_name(self) -> str:
        return "ultralytics"
    
    @property
    def plugin_type(self) -> str:
        return "downloader"
    
    def can_handle(self, model_name: str, **kwargs) -> bool:
        """Check if this plugin can handle the given model"""
        if model_name.startswith("ultralytics:"):
            return True
        
        # Check if the model is in the list of supported models
        try:
            supported_models = self.get_supported_models()
            model_without_prefix = model_name.split(":")[-1] if ":" in model_name else model_name
            return model_without_prefix in supported_models or model_without_prefix == "all"
        except:
            return False
    
    def download(self, model_name: str, output_dir: str, progress_callback=None, **kwargs) -> Dict[str, Any]:
        """Download the model using the bash script"""
        # Remove prefix if present
        model_without_prefix = model_name.split(":")[-1] if ":" in model_name else model_name
        
        # Extract quantization from kwargs
        quantize = kwargs.get("quantize", "")
        
        # Call the download script
        return_code = self._call_bash_script(model=model_without_prefix, quantize=quantize, models_path=output_dir)
        
        if return_code != 0:
            raise RuntimeError(f"Failed to download Ultralytics model {model_name}")
        
        return {
            "model_name": model_name,
            "source": "ultralytics",
            "download_path": output_dir,
            "return_code": return_code
        }
    
    def get_supported_models(self) -> List[str]:
        """Get list of supported models from the bash script"""
        script_path = Path(__file__).parent.parent.parent / "scripts" / "download_models_ultralytics.sh"
        
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
        script_path = Path(__file__).parent.parent.parent / "scripts" / "download_models_ultralytics.sh"
        
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
        """Call the download_models_ultralytics.sh bash script with arguments"""
        # Find script path relative to this file
        script_path = str(Path(__file__).parent.parent.parent / "scripts" / "download_models_ultralytics.sh")

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Bash script not found at {script_path}")

        cmd = ["bash", str(script_path), model]
        if quantize:
            cmd.append(quantize)

        logger.info(f"Executing: {' '.join(cmd)}")

        # Prepare environment with MODELS_PATH
        env = os.environ.copy()
        if models_path:
            env["MODELS_PATH"] = models_path
            logger.info(f"Using MODELS_PATH={models_path}")
        elif "MODELS_PATH" not in env:
            # Default to models/ directory in the current working directory
            default_models_path = str(Path.cwd() / "models")
            env["MODELS_PATH"] = default_models_path
            logger.info(f"MODELS_PATH not set, using default: {default_models_path}")

        # Execute the bash script and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
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
        if return_code != 0:
            logger.error(f"Script execution failed with return code {return_code}")

        return return_code