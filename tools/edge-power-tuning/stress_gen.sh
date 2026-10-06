#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# stress_gen.sh - Stress a configurable number of CPUs (and the iGPU) at a
# configurable percentage load.
#
# This script generates a SIMULATED load (via stress-ng) for evaluation
# purposes. You can use it to exercise a power profile/cap, or instead run the
# ACTUAL workload you want to evaluate -- either produces load the power monitor
# can observe.
#
# Usage: ./stress_gen.sh [--cpus N] [--load P] [--duration D] [--gpu N]
#   --cpus N      number of CPU workers, 1..$(nproc) (default: all CPUs)
#   --load P      per-CPU load percentage, 1..100 (default 100)
#   --duration D  optional stress-ng timeout, e.g. 60s, 5m (default: until Ctrl-C)
#   --gpu N       number of stress-ng GPU worker processes, 0..12 (default 4; 0 = off).
#                 Recommended maximum: 4 for a 4 Xe-core iGPU; 12 for a 12 Xe-core iGPU.
#                 NOTE: N is the count of GPU stressor workers, NOT the number of
#                 GPUs. They all target the single integrated GPU.
#   -h, --help    show this help and exit
#
# Examples:
#   ./stress_gen.sh                      # all CPUs at 100% + GPU, until Ctrl-C
#   ./stress_gen.sh --cpus 4 --load 50   # 4 CPUs at 50% load + GPU
#   ./stress_gen.sh --cpus 8 --load 75 --duration 2m --gpu 0   # CPU only

NCPU_MAX=$(nproc)
CPUS="$NCPU_MAX"
LOAD=100
DURATION=""
NGPU=4

usage() { sed -n '13,25p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
	case "$1" in
		-h|--help) usage; exit 0 ;;
		--cpus|--load|--duration|--gpu)
			[[ $# -ge 2 ]] || { echo "Error: $1 requires a value" >&2; exit 1; }
			case "$1" in
				--cpus)     CPUS="$2" ;;
				--load)     LOAD="$2" ;;
				--duration) DURATION="$2" ;;
				--gpu)      NGPU="$2" ;;
			esac
			shift 2 ;;
		--cpus=*)     CPUS="${1#*=}";     shift ;;
		--load=*)     LOAD="${1#*=}";     shift ;;
		--duration=*) DURATION="${1#*=}"; shift ;;
		--gpu=*)      NGPU="${1#*=}";     shift ;;
		*) echo "Error: unknown option '$1'" >&2; usage >&2; exit 1 ;;
	esac
done

if ! [[ "$LOAD" =~ ^[0-9]+$ ]] || (( LOAD < 1 || LOAD > 100 )); then
	echo "Error: --load must be an integer 1..100 (got '$LOAD')" >&2
	exit 1
fi
if ! [[ "$CPUS" =~ ^[0-9]+$ ]] || (( CPUS < 1 || CPUS > NCPU_MAX )); then
	echo "Error: --cpus must be an integer 1..${NCPU_MAX} (got '$CPUS')" >&2
	exit 1
fi
if ! [[ "$NGPU" =~ ^[0-9]+$ ]] || (( NGPU > 12 )); then
	echo "Error: --gpu must be an integer 0..12 (got '$NGPU')" >&2
	exit 1
fi

ARGS=(--cpu "$CPUS" --cpu-load "$LOAD")
(( NGPU > 0 )) && ARGS+=(--gpu "$NGPU")
[[ -n "$DURATION" ]] && ARGS+=(--timeout "$DURATION")

# Refuse to start if a stress-ng instance is already running, so we don't stack
# multiple stressors (which would skew the load and any power measurements).
if pgrep -x stress-ng >/dev/null 2>&1; then
	echo "Error: stress-ng is already running (PIDs: $(pgrep -x stress-ng | paste -sd,)). Stop it first (e.g. 'sudo pkill -x stress-ng')." >&2
	exit 1
fi

set -x
stress-ng "${ARGS[@]}"
