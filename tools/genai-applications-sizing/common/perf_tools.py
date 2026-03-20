# Copyright (C) 2024 Intel Corporation
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
import time

from common.constants import (
    PERF_TOOL_STOP_DELAY_SECONDS,
    DOCKER_REMOVAL_TIMEOUT_SECONDS
)


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
    compose_file = os.path.join(repo_name, 'docker', 'docker-compose-reg.yaml')
    
    # Create log directory
    log_dir = os.path.join(report_dir, "perf_tool_logs")
    abs_log_dir = os.path.abspath(log_dir)
    os.makedirs(abs_log_dir, exist_ok=True)

    try:
        # Clean up existing repository
        if os.path.exists(repo_name):
            if os.path.isdir(repo_name):
                shutil.rmtree(repo_name)
            else:
                os.remove(repo_name)
        
        # Clone the specific branch
        print(f"Cloning performance-tools repository from {repo_url}...")
        subprocess.run(
            ['git', 'clone', repo_url, repo_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Prepare environment with log directory
        env = os.environ.copy()
        env['log_dir'] = abs_log_dir
        
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
    
    return abs_log_dir


def stop_perf_tool():
    """
    Stop and remove the performance monitoring Docker container.
    
    This function gracefully shuts down the metrics-collector Docker container
    that was started by the start_perf_tool function. It waits briefly to ensure
    any pending metrics are flushed before forcefully removing the container.
    """
    try:
        # Brief delay to ensure metrics are flushed
        time.sleep(PERF_TOOL_STOP_DELAY_SECONDS)
        
        # Force remove the metrics collector container
        subprocess.run(
            ["docker", "rm", "-f", "metrics-collector"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=DOCKER_REMOVAL_TIMEOUT_SECONDS
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
    scripts_base = "performance-tools/benchmark-scripts"
    
    qmasa_parser = os.path.abspath(os.path.join(scripts_base, "parse_qmassa_metrics_to_json.py"))
    graph_plotter = os.path.abspath(os.path.join(scripts_base, "usage_graph_plot.py"))
    
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
    if not os.path.exists(logs_dir):
        print(f"Logs directory {logs_dir} does not exist.")
        return None
    
    try:
        report_logs_dir = os.path.join(report_dir, "perf_tools_logs")
        os.makedirs(report_logs_dir, exist_ok=True)
        
        for file in os.listdir(logs_dir):
            src_file = os.path.join(logs_dir, file)
            dest_file = os.path.join(report_logs_dir, file)
            if os.path.isfile(src_file):
                with open(src_file, 'rb') as fsrc, open(dest_file, 'wb') as fdest:
                    fdest.write(fsrc.read())
        return report_logs_dir
    except Exception as e:
        print(f"Failed to copy logs: {e}")
        return None
