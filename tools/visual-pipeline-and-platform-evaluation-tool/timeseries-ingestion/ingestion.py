#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import csv
import json
import os
import requests
import time
import socket

host = os.getenv("HOST", "ia-time-series-analytics-microservice")
port = os.getenv("PORT", "5000")
topic = os.getenv("TOPIC", "point_data")
metadata_dir = os.getenv("METADATA_DIR", "/metadata")
metadata_file = os.path.join(metadata_dir, "timeseries-ingestion.jsonl")

def is_port_open(host, port, timeout=3):
    retries = 0
    while(retries < 10):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (socket.timeout, socket.error) as e:
            pass
            time.sleep(1)
            retries += 1
    if retries == 10:
        print(f"Failed to connect to {host}:{port} after multiple attempts.")
        return False

if not port.isdigit():
    print(f"Invalid port number: {port}. Please provide a valid port number.")
    exit(1)
port = int(port)
if not is_port_open(host, port):
    print(f"Port {port} on {host} is not accessible.")
    exit(1)
else:
    print(f"Port {port} on {host} is accessible.")

def wait_for_health(host, port, delay=5):
    health_url = f"http://{host}:{port}/health"
    attempt = 1
    while True:
        try:
            response = requests.get(health_url, timeout=5)
            if response.status_code in (200, 204):
                print(f"Health check passed (HTTP {response.status_code}).")
                return
            else:
                print(f"Health check attempt {attempt}: status {response.status_code}. Retrying in {delay}s...")
        except requests.exceptions.RequestException as e:
            print(f"Health check attempt {attempt} failed: {e}. Retrying in {delay}s...")
        time.sleep(delay)
        attempt += 1

wait_for_health(host, port)

url = f"http://{host}:{port}/input"

headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
}

csv_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "input", "input.csv")


def write_metadata(fields, status_code):
    """Write ingestion data to a shared metadata JSONL file."""
    record = {
        "timestamp": time.time(),
        "type": "ingestion",
        "data": fields,
        "status": status_code,
    }
    try:
        os.makedirs(os.path.dirname(metadata_file), exist_ok=True)
        with open(metadata_file, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        print(f"Warning: Could not write metadata: {e}")


def send_data(filepath):
    while True:
        with open(filepath, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fields = {col: float(row[col]) for col in reader.fieldnames}
                payload = {"topic": topic, "fields": fields}
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=10)
                    print(f"Sent: {fields} | Status: {response.status_code}")
                    write_metadata(fields, response.status_code)
                    if response.status_code in (200, 204):
                        print("Write successful.")
                    else:
                        print(f"Response Body: {response.text}")
                except requests.exceptions.ConnectionError as e:
                    print(f"Connection error, service unavailable. Retrying in 10s... ({e})")
                    time.sleep(10)
                    continue
                except requests.exceptions.Timeout:
                    print(f"Request timed out. Retrying in 5s...")
                    time.sleep(5)
                    continue
                time.sleep(5)

send_data(csv_file)