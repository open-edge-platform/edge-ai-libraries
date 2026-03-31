# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Performance monitoring tool management utilities.

This module provides functions for starting, stopping, and managing
Docker-based performance monitoring tools for collecting CPU, GPU,
and memory metrics during profiling runs.
"""

import os
import shutil
import subprocess
from pathlib import Path
import time


def start_perf_tool(repo_url, report_dir):
    """
    Initialize and start the performance monitoring tool in a Docker container.
    
    This function clones the performance-tools repository, sets up the log
    directory, and starts the metrics-collector container via docker-compose.
    
    Args:
        repo_url: Git repository URL for the performance-tools repo.
        report_dir: Path to the report directory where performance logs
                   will be stored.
    
    Returns:
        str: Absolute path to the log directory where performance metrics are stored.
    """
    repo_name = "performance-tools"
    compose_file = Path(repo_name) / 'docker' / 'docker-compose-reg.yaml'
    
    # Create log directory
    abs_log_dir = (Path(report_dir) / "perf_tool_logs").resolve()
    abs_log_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Clean up existing repository
        if Path(repo_name).exists():
            if Path(repo_name).is_dir():
                shutil.rmtree(repo_name)
            else:
                Path(repo_name).unlink()
        
        # Clone the repo from main branch
        print(f"Cloning performance-tools repository from {repo_url}...")
        subprocess.run(
            ['git', 'clone', repo_url, repo_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Prepare environment with log directory
        env = os.environ.copy()
        env['log_dir'] = str(abs_log_dir)
        
        # Start docker compose with wait flag
        print("Starting performance monitoring containers, it takes some time to initialize...")
        subprocess.run(
            ['docker', 'compose', '-f', compose_file, 'up', '-d', '--wait'],
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )        
        print(f"Performance tool started. Logs directory: {abs_log_dir}")
        
    except subprocess.CalledProcessError as e:
        print(f"Error during performance tool setup: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr.decode('utf-8', errors='ignore')}")
    except OSError as e:
        print(f"File system error during performance tool setup: {e}")
    except Exception as e:
        print(f"Unexpected error during performance tool setup: {e}")
    
    return str(abs_log_dir), compose_file


def stop_perf_tool(compose_file, log_dir):
    """
    Stop and remove the performance monitoring Docker services.
    
    This function gracefully shuts down all services defined in the compose file
    that were started by the start_perf_tool function. It waits briefly to ensure
    any pending metrics are flushed before stopping and removing the services.
    
    Args:
        compose_file: Path to the docker-compose file used to start the services.
        log_dir: Path to the log directory, passed as the log_dir environment variable.
    """
    try:
        # Brief delay to ensure metrics are flushed
        time.sleep(2)
        
        # Prepare environment with log directory
        env = os.environ.copy()
        env['log_dir'] = str(log_dir)
        
        # Stop and remove all services defined in the compose file
        subprocess.run(
            ["docker", "compose", "-f", compose_file, "down"],
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        
        print("Performance tool stopped.")
        
    except subprocess.TimeoutExpired:
        print("Warning: Docker container removal timed out.")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"Error stopping performance tool: {error_msg}")
    except FileNotFoundError:
        print("Error: Docker command not found. Ensure Docker is installed and in PATH.")
    except Exception as e:
        print(f"Unexpected error stopping performance tool: {e}")


def plot_graphs(log_dir):
    """
    Generate performance visualization graphs from collected metrics logs.
    
    This function parses QMASA metrics from the log directory and generates
    usage graphs for visualization.
    
    Args:
        log_dir: Path to the directory containing raw performance metrics logs.
    """
    scripts_base = Path("performance-tools/benchmark-scripts")
    
    qmasa_parser = (scripts_base / "parse_qmassa_metrics_to_json.py").resolve()
    graph_plotter = (scripts_base / "usage_graph_plot.py").resolve()
    
    try:
        subprocess.run(
            ['python3', qmasa_parser, '--dir', log_dir],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        
        print(f"Generating usage graphs from {log_dir}...")
        subprocess.run(
            ['python3', graph_plotter, '--dir', log_dir],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        
        print(f"Performance graphs successfully generated in: {log_dir}")
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"Plot graph failed with subprocess error: {error_msg}")
    except FileNotFoundError as e:
        print(f"Error: Required script not found. Ensure performance-tools repo is cloned: {e}")
    except Exception as e:
        print(f"Unexpected error during graph generation: {e}")


def copy_perf_tools_logs(logs_dir, report_dir):
    """
    Copy performance tools logs to the report directory.
    
    Args:
        logs_dir: Source directory containing performance logs.
        report_dir: Destination report directory.
        
    Returns:
        str: Path to the copied logs directory, or None on error.
    """
    if not Path(logs_dir).exists():
        print(f"Logs directory {logs_dir} does not exist.")
        return None
    
    try:
        report_logs_dir = Path(report_dir) / "perf_tools_logs"
        report_logs_dir.mkdir(parents=True, exist_ok=True)
        
        for src_file in Path(logs_dir).iterdir():
            dest_file = report_logs_dir / src_file.name
            if src_file.is_file():
                with src_file.open('rb') as fsrc, dest_file.open('wb') as fdest:
                    fdest.write(fsrc.read())
        return str(report_logs_dir)
    except Exception as e:
        print(f"Failed to copy logs: {e}")
        return None
