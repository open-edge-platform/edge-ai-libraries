#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import requests
import random
import time
import socket
import argparse

parser = argparse.ArgumentParser(description="Send temperature data to Time Series Analytics Microservice.")
parser.add_argument(
    "--mode",
    choices=["helm", "docker"],
    required=True,
    help="Deployment mode: 'helm' or 'docker'"
)
args = parser.parse_args()

print(f"Running in {args.mode} mode.")

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
    
host = "localhost"

if args.mode == "helm":
    port = 30009
else:
    port = 9092

if not is_port_open(host, port):
    print(f"Port {port} on {host} is not accessible.")
    exit(1)
else:
    print(f"Port {port} on {host} is accessible.") 

url = f"http://localhost:{port}/kapacitor/v1/write"
params = {
    "db": "datain",
    "rp": "autogen"
}
# Generate random values: some <20, some >25, all between 10 and 50
for i in range(1, 500):
    if i % 10 == 0:
        # Every 10th value: between 20 and 25 (inclusive)
        value = random.randint(20, 25)
    else:
        value = random.randint(10, 50)
 
    payload = f"point_data temperature={value}"
    headers = {
        "Content-Type": "text/plain"
    }
 
    response = requests.post(url, params=params, data=payload, headers=headers)
  
    print(f"Sent value: {value}")
    print(f"Status Code: {response.status_code}")
    if response.status_code != 204:
        print(f"Response Body: {response.text}")
    else:
        print("Write successful.")
    time.sleep(5)
