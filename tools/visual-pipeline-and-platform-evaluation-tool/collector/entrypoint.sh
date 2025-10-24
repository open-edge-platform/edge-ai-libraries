#!/bin/bash

# Endure the fps.txt file exists and is initialized to 0.0
echo "0.0" > /app/.collector-signals/fps.txt

# Start telegraf with the specified configuration file
/usr/bin/telegraf --config /etc/telegraf/telegraf.conf
