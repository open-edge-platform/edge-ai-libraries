#!/bin/bash

ACTION=$1  # "start" or "stop"
NUM_INSTANCES=$2
INPUT_VIDEO=$3
SYSTEM_IP=$4
BASE_PORT=8555

if [ "$ACTION" == "start" ]; then
  # Loop to start multiple cvlc instances
  for ((i=0; i<NUM_INSTANCES; i++))
  do
    PORT=$((BASE_PORT + i))
    echo "Starting RTSP server on port $PORT"
    nohup cvlc -vvv file://$INPUT_VIDEO --sout "#gather:rtp{sdp=rtsp://$SYSTEM_IP:$PORT/live.sdp}" --loop --sout-keep > cvlc_$PORT.log 2>&1 &
    echo $! >> vlc_pids.txt  # Store process IDs
  done
  echo "All cvlc instances started in the background."

elif [ "$ACTION" == "stop" ]; then
  echo "Stopping all cvlc instances..."
  if [ -f vlc_pids.txt ]; then
    while read -r pid; do
      kill "$pid"
    done < vlc_pids.txt
    rm vlc_pids.txt
    echo "All cvlc instances stopped."
  else
    echo "No vlc_pids.txt file found. Killing all cvlc processes."
    pkill -f cvlc
  fi
else
  echo "Usage: $0 {start|stop} [NUM_INSTANCES] [INPUT_VIDEO] [SYSTEM_IP]"
fi