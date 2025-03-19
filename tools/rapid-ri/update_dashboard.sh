#!/bin/bash

# Load environment variables
if [ -f .env ]; then
  source .env
else
  echo "Error: .env file not found!"
  exit 1
fi

# Check for required variables
if [ -z "$Case" ]; then
  echo "Error: Case environment variable is not set."
  exit 1
fi

if [ -z "$HOST_IP" ]; then
  echo "Error: HOST_IP environment variable is not set."
  exit 1
fi

echo "Updating configuration for case: $Case"

#############################################
# Update dashboard JSON files IP address  #
#############################################

# Prefer the new usecase folder, then legacy grafana folder
if [ -d "./usecase/$Case/grafana/dashboards" ]; then
  DASH_DIR="./usecase/$Case/grafana/dashboards"
  echo "Found usecase dashboards folder: $DASH_DIR"
elif [ -d "./grafana/dashboards" ]; then
  DASH_DIR="./grafana/dashboards"
  echo "Using legacy grafana dashboards folder: $DASH_DIR"
else
  echo "Warning: No dashboards folder found."
  DASH_DIR=""
fi

if [ -n "$DASH_DIR" ]; then
  for file in "$DASH_DIR"/*.json; do
    [ -f "$file" ] && sed -i "s|\"url\": *\"http://[0-9]\{1,3\}\(\.[0-9]\{1,3\}\)\{3\}:|\"url\": \"http://$HOST_IP:|g" "$file" 
    sed -i "s|\"mqttLink\": *\"ws://[0-9]\{1,3\}\(\.[0-9]\{1,3\}\)\{3\}:|\"mqttLink\": \"ws://$HOST_IP:|g" "$file" 
  sed -i "s|\"webrtcUrl\": *\"http://[0-9]\{1,3\}\(\.[0-9]\{1,3\}\)\{3\}:|\"webrtcUrl\": \"http://$HOST_IP:|g" "$file"
  done
fi

#############################################
# Update datasources.yml file IP address  #
#############################################

# Check for the new location first, then legacy location
if [ -f "./usecase/$Case/grafana/datasources.yml" ]; then
  DS_FILE="./usecase/$Case/grafana/datasources.yml"
  echo "Found usecase datasources file: $DS_FILE"
elif [ -f "./grafana/datasources.yml" ]; then
  DS_FILE="./grafana/datasources.yml"
  echo "Using legacy grafana datasources file: $DS_FILE"
else
  DS_FILE=""
  echo "Warning: No datasources.yml file found."
fi

if [ -n "$DS_FILE" ]; then
  sed -i "s|tcp://[0-9]\{1,3\}\(\.[0-9]\{1,3\}\)\{3\}:1883|tcp://$HOST_IP:1883|g" "$DS_FILE"
fi

#############################################
# Update Node-RED flows IP address          #
#############################################

# Check for the new location first, then legacy location
if [ -f "./usecase/$Case/node-red/flows.json" ]; then
  NR_FILE="./usecase/$Case/node-red/flows.json"
  echo "Found usecase node-red flows file: $NR_FILE"
elif [ -f "./node-red/flows.json" ]; then
  NR_FILE="./node-red/flows.json"
  echo "Using legacy node-red flows file: $NR_FILE"
else
  NR_FILE=""
  echo "Warning: No node-red flows file found."
fi

if [ -n "$NR_FILE" ]; then
  sed -i "s|http://[0-9]\{1,3\}\(\.[0-9]\{1,3\}\)\{3\}|http://$HOST_IP|g" "$NR_FILE"
  sed -i "s|\"broker\": *\"[0-9]\{1,3\}\(\.[0-9]\{1,3\}\)\{3\}\",|\"broker\": \"$HOST_IP\",|" "$NR_FILE"
fi

#############################################
# Update run_sample.sh for video paths and  #
# MQTT host IP                              #
#############################################

# Check if the run_sample.sh exists in the usecase folder for the current case
if [ -f "./usecase/$Case/run_sample.sh" ]; then
  echo "Found run_sample.sh in usecase/$Case. Copying to root directory..."
  cp "./usecase/$Case/run_sample.sh" "./run_sample.sh"
  
  # Update the video source path to point to the usecase folder
  sed -i "s|file:///home/pipeline-server/videos/|file:///home/pipeline-server/videos/|g" ./run_sample.sh
  
  # Update the MQTT host IP in the file
  sed -i "s|\"host\": *\"[0-9]\{1,3\}\(\.[0-9]\{1,3\}\)\{3\}:|\"host\": \"$HOST_IP:|g" ./run_sample.sh
  
  echo "Updated run_sample.sh copied from usecase/$Case."
else
  echo "Warning: run_sample.sh not found in usecase/$Case folder"
fi