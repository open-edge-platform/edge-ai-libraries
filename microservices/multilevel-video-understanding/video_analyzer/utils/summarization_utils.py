# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from functools import wraps
from typing import Callable, Any
from video_analyzer.utils.logger import logger

"""
Utility functions for video summarization.
"""
import re
import os
from typing import List, Any, Dict, Union


def redact_base64(data: Union[str, List[Dict[str, Any]]]) -> Union[str, List[Dict[str, Any]]]:
    """
    Replace long base64 blobs with a short placeholder for readable console output.

    Supports:
    - str: returns redacted string
    - List[Dict[str, Any]]: scans each dict value; redacts any string values containing long base64
    """
    pattern = re.compile(r"[A-Za-z0-9+/=]{80,}")

    def _redact_str(s: str) -> str:
        def repl(m):
            blob = m.group(0)
            return f"<BASE64:{blob[:12]}...len={len(blob)}>"
        return pattern.sub(repl, s)

    def _redact_obj(obj: Any) -> Any:
        if isinstance(obj, str):
            return _redact_str(obj)
        elif isinstance(obj, dict):
            return {k: _redact_obj(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_redact_obj(x) for x in obj]
        else:
            return obj

    return _redact_obj(data)

def remove_brackets(text: str) -> str:
    """
    Remove outer brackets from text.

    Args:
        text: The text to process

    Returns:
        Text with outer brackets removed
    """
    while True:
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        else:
            break
    return text

def uniform_sample(items: List[Any], n: int) -> List[Any]:
    """
    Uniformly sample n items from a list.

    Args:
        items: The list to sample from
        n: Number of items to sample

    Returns:
        List of sampled items
    """
    gap = len(items) / n
    idxs = [int(i * gap + gap / 2) for i in range(n)]
    return [items[i] for i in idxs]


def ensure_output_file_exists() -> None:
    """
    Ensure the output file exists and is empty.
    """
    if os.path.exists("output.txt"):
        os.remove("output.txt")
        print("output.txt has been removed.")


def warn_unused_kwargs(func: Callable) -> Callable:
    """
    Decorator: Detect unused kwargs parameters in functions and issue warnings
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get the parameters of the function definition
        import inspect
        sig = inspect.signature(func)
        defined_params = set(sig.parameters.keys())
        
        # Get the actual keyword parameters passed in
        passed_kwargs = set(kwargs.keys())
        
        # Calculate unused parameters
        unused_kwargs = passed_kwargs - defined_params
        if unused_kwargs:
            logger.warning(
                f"Function {func.__name__} will ignore unused kwargs: {', '.join(sorted(unused_kwargs))}",
            )
        
        return func(*args, **kwargs)
    return wrapper
