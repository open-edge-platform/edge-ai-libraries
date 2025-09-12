import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict
from src.utils.logging import logger

def call_bash_script(model: str = "all", quantize: str = "", models_path: str = "") -> int:
    """
    Call the download_models_ultralytics.sh bash script with arguments.
    
    Args:
        model: Model name to download (as defined in SUPPORTED_MODELS in the bash script)
        quantize: Quantization dataset to use (as defined in SUPPORTED_QUANTIZATION_DATASETS)
        
    Returns:
        Return code from the script execution
    """
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
            logger.error(stderr_line.strip(), file=sys.stderr)
            
        if not stdout_line and not stderr_line and process.poll() is not None:
            break
    
    return_code = process.poll()
    if return_code != 0:
        logger.error(f"Script execution failed with return code {return_code}")

    return return_code

def get_supported_models() -> List[str]:
    """
    Get list of supported models from the bash script.
    
    Returns:
        List of supported model names
    """
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

def get_supported_quantization_datasets() -> Dict[str, str]:
    """
    Get dict of supported quantization datasets from the bash script.
    
    Returns:
        Dict of dataset names to URLs
    """
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

def download_model(model_name: str, quantize: str = "", models_path: str = "" ) -> int:
    """
    Download model using the bash script.
    
    Args:
        model_name: Model name to download (as specified in the bash script)
        quantize: Optional quantization dataset
        
    Returns:
        Return code from script execution
    """
    return call_bash_script(model=model_name, quantize=quantize,models_path=models_path)

def get_model_path(model_name: str, path: str) -> str:
    """
    Get the path to a downloaded model.
    
    Args:
        model_name: Name of the model
        path: Base path where the model is located
        
    Returns:
        Path to the model file
    """
    # models_path = os.environ.get("MODELS_PATH", "")
    # if not models_path:
    #     raise EnvironmentError("MODELS_PATH environment variable not set")
    
    # Try to find the model in common directories
    possible_paths = [
        Path(path) / "public" / model_name / "FP32" / f"{model_name}.xml",
        Path(path) / "public" / model_name / "FP16" / f"{model_name}.xml",
        Path(path) / "public" / model_name / "INT8" / f"{model_name}.xml"
    ]
    models_path = Path(path)
    if not models_path.exists():
        raise FileNotFoundError(f"Models path {models_path} does not exist")
    for paths in possible_paths:
        if paths.exists():
            return str(paths)

    raise FileNotFoundError(f"Model {model_name} not found in {models_path}")

def main():
    parser = argparse.ArgumentParser(description="Ultralytics model downloader")
    parser.add_argument("--model", type=str, default="all", 
                        help="Model to download (must be in SUPPORTED_MODELS in bash script)")
    parser.add_argument("--quantize", type=str, default="",
                        help="Quantization dataset to use (must be in SUPPORTED_QUANTIZATION_DATASETS)")
    parser.add_argument("--list-models", action="store_true",
                        help="List all supported models")
    parser.add_argument("--list-datasets", action="store_true",
                        help="List all supported quantization datasets")
    parser.add_argument("--path", type=str, default="",
                        help="Set the path where the model need to be downloaded")
       
    args = parser.parse_args()
    
    # List models or datasets if requested
    if args.list_models:
        models = get_supported_models()
        logger.info("Supported models:")
        for model in models:
            logger.info(f"  - {model}")
        return 0
        
    if args.list_datasets:
        datasets = get_supported_quantization_datasets()
        logger.info("Supported quantization datasets:")
        for dataset, url in datasets.items():
            logger.info(f"  - {dataset}: {url}")
        return 0
    
    # Call the bash script to download the model
    return_code = download_model(args.model, args.quantize,args.path)
    
    if return_code != 0:
        logger.error("Model download failed")
        return return_code
    
    return 0

if __name__ == "__main__":
    sys.exit(main())