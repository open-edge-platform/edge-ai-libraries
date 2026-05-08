import subprocess
from typing import Callable, List
import logging
logger = logging.getLogger(__name__)

def run_cli(cmd: List[str], log_fn: Callable[[str], None] = print) -> int:
    """
    Run a CLI command and stream stdout + stderr in real-time.

    Args:
        cmd: Command as a list of strings, e.g., ["python", "script.py"]
        log_fn: Function to log each line (default: print)

    Returns:
        The CLI process return code
    """
    try:
        logger.info(f"Running: {cmd}")
        env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # line-buffered
            env=env,
        )

        # Stream output line by line
        for line in iter(process.stdout.readline, ''):
            log_fn(line.rstrip())

        process.stdout.close()
        return process.wait()

    except Exception as e:
        log_fn(f"❌ Command execution failed: {e}")
        return -1
