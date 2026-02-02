#!/bin/bash

exec uvicorn api.main:app --host 0.0.0.0 --port 7860 --ws-ping-interval 10 --ws-ping-timeout 30
