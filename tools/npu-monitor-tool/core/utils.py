import logging as LOG
import subprocess  # nosec B404
import shlex
import sys

from typing import Optional

def fdump(path: str) -> str:
    """Read and return the contents of a file, with error handling."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        LOG.error('File not found: %s', path)
        sys.exit(1)
    except PermissionError:
        LOG.error('Permission denied reading: %s', path)
        sys.exit(1)
    except Exception as e:
        LOG.error('Error reading %s: %s', path, e)
        sys.exit(1)

def run_command(command: str, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    """Execute a shell command safely without shell=True."""
    try:
        cmd_list = shlex.split(command)
        # Uses argument list + default shell=False (no shell expansion).
        return subprocess.run(  # nosec B603
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=True,
            encoding='ascii',
            errors='ignore',
        )
    except subprocess.TimeoutExpired as err:
        return subprocess.CompletedProcess(command, 1, err.stdout or '')
    except subprocess.CalledProcessError as err:
        return subprocess.CompletedProcess(command, err.returncode, err.stdout or '')
    except FileNotFoundError:
        return subprocess.CompletedProcess(command, 127, 'Executable not found')
    except OSError as err:
        return subprocess.CompletedProcess(command, 1, f'Execution failed: {err}')
