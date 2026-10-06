#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# openvino_stress.sh — Generate sustained AI inference load on CPU, GPU, or NPU
# using OpenVINO benchmark_app. Supports K3s (pods) and Docker runtimes.
# Designed to pair with pt_mon.sh for power/thermal measurement.

set -euo pipefail

# ── Defaults ──
DEVICE="cpu"  RUNTIME=""  NITER="0"  DURATION="60"  NTHREADS=""  API_MODE="sync"
MODEL_PATH="/home/user/models/intel"
OV_IMAGE="openvino/ubuntu24_dev:2026.0.0"
MODEL_SUBPATH="intel/age-gender-recognition-retail-0013/FP16/age-gender-recognition-retail-0013.xml"
CLEANUP=false
DEFAULT_MODEL_SUBPATH="intel/age-gender-recognition-retail-0013/FP16/age-gender-recognition-retail-0013.xml"
DEFAULT_MODEL_XML_SHA256="347b51acfce3ddf3d9a1e6e1ccd16a1d130c1fb009c647a35243d0919d18c8d4"
DEFAULT_MODEL_BIN_SHA256="59095b3440e09d93e92c5ee79cafeeafc11a3c292a5d6133efe6a34b9d554916"

# --device gpu always runs natively via pip; OV_IMAGE's bundled GPU runtime is too old for this silicon.
GPU_VENV_DIR="${GPU_VENV_DIR:-$HOME/.cache/openvino-stress/venv}"
GPU_RUN_DIR="/tmp/openvino-stress"

die() { echo "Error: $1" >&2; exit 1; }

verify_sha256() {
    local expected_hash="$1" file_path="$2"
    printf '%s  %s\n' "$expected_hash" "$file_path" | sha256sum --check --status -
}

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Generate sustained AI inference load using OpenVINO benchmark_app.

OPTIONS:
  --device <cpu|gpu|npu>   Target device (default: cpu)
  --runtime <k3s|docker>   Container runtime for cpu/npu (default: auto-detect); ignored for gpu, which always runs natively via pip
  --niter <N>              Iterations; 0 = time-based (default: 0)
  --duration <seconds>     Duration when niter=0 (default: 60)
  --nthreads <N>           CPU threads for inference (default: auto)
  --api <sync|async>       Inference API mode (default: sync)
  --model-path <path>      Host path to models dir
  --model <subpath>        Model subpath within model-path
  --image <image:tag>      OpenVINO container image
  --cleanup                Stop and remove running benchmark containers/pods
  -h, --help               Show this help

EXAMPLES:
  $(basename "$0") --device cpu --duration 120
  $(basename "$0") --device gpu --duration 300
  $(basename "$0") --device npu --niter 500000
  $(basename "$0") --runtime docker --device npu --duration 60
  $(basename "$0") --cleanup
EOF
    exit 0
}

# ── Argument parsing ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --device|--runtime|--niter|--duration|--nthreads|--api|--model-path|--model|--image)
            KEY="${1#--}"; KEY="${KEY//-/_}"
            case "$KEY" in
                model_path) MODEL_PATH="$2" ;; model) MODEL_SUBPATH="$2" ;;
                image) OV_IMAGE="$2" ;; api) API_MODE="$2" ;;
                *) declare "${KEY^^}=$2" ;;
            esac
            shift 2 ;;
        --cleanup) CLEANUP=true; shift ;;
        -h|--help) usage ;;
        *) die "Unknown option '$1'. Use --help." ;;
    esac
done

# ── Validation ──
[[ "$DEVICE" =~ ^(cpu|gpu|npu)$ ]] || die "--device must be cpu, gpu, or npu"
[[ "$API_MODE" =~ ^(sync|async)$ ]] || die "--api must be sync or async"
[[ "$NITER" =~ ^[0-9]+$ ]]          || die "--niter must be a non-negative integer"
if ! [[ "$DURATION" =~ ^[0-9]+$ ]] || (( DURATION < 1 )); then
    die "--duration must be a positive integer"
fi
[[ -z "$NTHREADS" || ( "$NTHREADS" =~ ^[0-9]+$ && NTHREADS -ge 1 ) ]] || die "--nthreads must be a positive integer"

# ── Runtime auto-detection ──
if [[ "$DEVICE" == "gpu" ]]; then
    RUNTIME="${RUNTIME:-pip}"
elif [[ -n "$RUNTIME" ]]; then
    [[ "$RUNTIME" =~ ^(k3s|docker)$ ]] || die "--runtime must be k3s or docker"
elif command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    RUNTIME="docker"
elif command -v kubectl &>/dev/null && kubectl cluster-info &>/dev/null 2>&1; then
    RUNTIME="k3s"
else
    die "Neither K3s (kubectl) nor Docker detected"
fi

NAME="openvino-stress-${DEVICE}"

# ── Cleanup ──
if $CLEANUP; then
    echo "Cleaning up OpenVINO stress workloads..."
    for dev in cpu gpu npu; do
        if [[ "$dev" == "gpu" ]]; then
            pidfile="${GPU_RUN_DIR}/openvino-stress-gpu.pid"
            [[ -f "$pidfile" ]] && { kill "$(cat "$pidfile")" 2>/dev/null || true; rm -f "$pidfile"; }
        elif [[ "$RUNTIME" == "k3s" ]]; then
            kubectl delete pod "openvino-stress-${dev}" --ignore-not-found --wait=false 2>/dev/null || true
        else
            docker rm -f "openvino-stress-${dev}" 2>/dev/null || true
        fi
    done
    echo "Done."
    exit 0
fi

# ── Remove any existing instance before launching ──
if [[ "$DEVICE" == "gpu" ]]; then
    pidfile="${GPU_RUN_DIR}/${NAME}.pid"
    [[ -f "$pidfile" ]] && { kill "$(cat "$pidfile")" 2>/dev/null || true; rm -f "$pidfile"; }
elif [[ "$RUNTIME" == "k3s" ]]; then
    kubectl delete pod "$NAME" --ignore-not-found --wait=false 2>/dev/null || true
    kubectl wait --for=delete pod/"$NAME" --timeout=30s 2>/dev/null || true
else
    docker rm -f "$NAME" 2>/dev/null || true
fi

# ── Model path validation / auto-download ──
MODEL_BASE_URL="https://storage.openvinotoolkit.org/repositories/open_model_zoo/2022.3/models_bin/1"
MODEL_FILE="${MODEL_PATH}/${MODEL_SUBPATH}"

if [[ ! -f "$MODEL_FILE" ]]; then
    [[ "$MODEL_SUBPATH" == "$DEFAULT_MODEL_SUBPATH" ]] || die "Automatic download is available only for the pinned default model; download and verify custom models before use"
    echo "Model not found at ${MODEL_FILE}"
    echo "Downloading model via curl..."
    _MODEL_NAME="age-gender-recognition-retail-0013"
    _MODEL_PREC="FP16"
    _MODEL_DIR="${MODEL_PATH}/intel/${_MODEL_NAME}/${_MODEL_PREC}"
    mkdir -p "$_MODEL_DIR"
    for ext in xml bin; do
        if [[ "$ext" == "xml" ]]; then expected_hash="$DEFAULT_MODEL_XML_SHA256"; else expected_hash="$DEFAULT_MODEL_BIN_SHA256"; fi
        target_file="${_MODEL_DIR}/${_MODEL_NAME}.${ext}"
        temporary_file="${target_file}.download.$$"
        curl -fSL "${MODEL_BASE_URL}/${_MODEL_NAME}/${_MODEL_PREC}/${_MODEL_NAME}.${ext}" \
            -o "$temporary_file" \
            || { rm -f "$temporary_file"; die "Failed to download ${_MODEL_NAME}.${ext} from ${MODEL_BASE_URL}"; }
        verify_sha256 "$expected_hash" "$temporary_file" \
            || { rm -f "$temporary_file"; die "Checksum verification failed for ${_MODEL_NAME}.${ext}"; }
        mv -f "$temporary_file" "$target_file"
    done
    [[ -f "$MODEL_FILE" ]] || die "Model download failed"
    echo "Model downloaded to ${_MODEL_DIR}"
fi

if [[ "$MODEL_SUBPATH" == "$DEFAULT_MODEL_SUBPATH" ]]; then
    verify_sha256 "$DEFAULT_MODEL_XML_SHA256" "$MODEL_FILE" || die "Checksum verification failed for default model XML"
    verify_sha256 "$DEFAULT_MODEL_BIN_SHA256" "${MODEL_FILE%.xml}.bin" || die "Checksum verification failed for default model BIN"
fi

# ── Build benchmark command ──
# gpu references the host model path directly; cpu/npu use the container mount (/models).
if [[ "$DEVICE" == "gpu" ]]; then
    BM_CMD="benchmark_app -m ${MODEL_FILE} -d ${DEVICE^^}"
else
    BM_CMD="benchmark_app -m /models/${MODEL_SUBPATH} -d ${DEVICE^^}"
fi
if (( NITER > 0 )); then BM_CMD+=" -niter $NITER"; else BM_CMD+=" -t $DURATION"; fi
BM_CMD+=" -api $API_MODE"
if [[ "$DEVICE" != "npu" ]]; then
    BM_CMD+=" -nthreads ${NTHREADS:-$([ "$DEVICE" = "gpu" ] && echo 2 || echo 0)}"
fi
[[ "$DEVICE" == "gpu" ]] && BM_CMD+=" -hint none"

# ── Display summary ──
echo ""
echo "  Device: ${DEVICE^^} | Runtime: ${RUNTIME} | API: ${API_MODE}"
if (( NITER > 0 )); then echo "  Iterations: ${NITER}"; else echo "  Duration: ${DURATION}s"; fi
echo "  Command: ${BM_CMD}"
echo ""

# ════════════════════════════════════════════════════════════════════════════════
# K3s pod YAML generator
# ════════════════════════════════════════════════════════════════════════════════

generate_pod_yaml() {
    local GID=44 SUPPL="" RESOURCES="" ENVS="" XMOUNTS="" XVOLS="" DEVCHK=""

    case "$DEVICE" in
        cpu) DEVCHK='nproc' ;;
        npu)
            GID=992; SUPPL="    supplementalGroups: [44, 992]"
            RESOURCES='    resources: { limits: { "npu.intel.com/accel": 1 } }'
            ENVS='    env:
    - { name: LD_LIBRARY_PATH, value: "/usr/local/lib:/opt/intel/openvino/runtime/lib/intel64:/opt/intel/openvino/runtime/3rdparty/tbb/lib:/usr/lib/x86_64-linux-gnu" }'
            XMOUNTS='    - { name: host-npu-firmware, mountPath: /lib/firmware/intel/vpu, readOnly: true }'
            XVOLS='  - { name: host-npu-firmware, hostPath: { path: /lib/firmware/intel/vpu, type: Directory } }'
            DEVCHK='ls -la /dev/accel/ 2>/dev/null || echo "No /dev/accel/"'
            ;;
    esac

    cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${NAME}
  labels: { app: openvino-stress, device: "${DEVICE}" }
spec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: ${GID}
${SUPPL:+${SUPPL}}
  containers:
  - name: benchmark
    image: ${OV_IMAGE}
    imagePullPolicy: IfNotPresent
    securityContext: { privileged: false, allowPrivilegeEscalation: false, capabilities: { drop: ["ALL"] } }
${RESOURCES:+${RESOURCES}}
${ENVS:+${ENVS}}
    volumeMounts:
    - { name: model-volume, mountPath: /models, readOnly: true }
${XMOUNTS:+${XMOUNTS}}
    command: ["/bin/bash", "-c"]
    args:
    - |
      echo "=== OpenVINO Stress: ${DEVICE^^} ==="
      ${DEVCHK}
      ${BM_CMD} 2>&1
      echo "=== Benchmark Complete ==="
  volumes:
  - { name: model-volume, hostPath: { path: "${MODEL_PATH}", type: Directory } }
${XVOLS:+${XVOLS}}
EOF
}

# ── Launch via K3s ──
launch_k3s() {
    generate_pod_yaml | kubectl apply -f -
    echo "Pod '$NAME' deployed. Waiting for Running..."

    for _ in $(seq 1 60); do
        PHASE=$(kubectl get pod "$NAME" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
        [[ "$PHASE" == "Running" || "$PHASE" == "Succeeded" ]] && break
        sleep 2
    done
    kubectl get pod "$NAME" --no-headers 2>/dev/null

    echo ""
    echo "Monitor: kubectl logs -f $NAME"
    echo "Stop:    kubectl delete pod $NAME"
}

# ── Launch via Docker ──
launch_docker() {
    local ARGS=(run -d --name "$NAME" -v "${MODEL_PATH}:/models:ro")

    if [[ "$DEVICE" == "npu" ]]; then
        if [[ -f /etc/cdi/intel.com-npu.yaml ]]; then
            ARGS+=(--device intel.com/npu=npu0)
        else
            for dev in /dev/accel/*; do [[ -e "$dev" ]] && ARGS+=(--device "$dev"); done
        fi
    fi

    ARGS+=("$OV_IMAGE" bash -c "${BM_CMD} 2>&1; echo '=== Benchmark Complete ==='")
    docker "${ARGS[@]}"

    docker ps --format '{{.Names}}' | grep -qx "$NAME" || die "Container failed to start"
    echo "Container '$NAME' running."
    echo ""
    echo "Monitor: docker logs -f $NAME"
    echo "Stop:    docker rm -f $NAME"
}

# ── Launch GPU natively via pip (host's OpenCL/Level Zero stack is newer than OV_IMAGE's) ──
ensure_gpu_pip_venv() {
    [[ -x "${GPU_VENV_DIR}/bin/benchmark_app" ]] && return
    echo "Setting up pip OpenVINO venv at ${GPU_VENV_DIR}..." >&2
    python3 -m venv "$GPU_VENV_DIR"
    "${GPU_VENV_DIR}/bin/pip" install --quiet --upgrade pip openvino
}

launch_gpu_native() {
    ensure_gpu_pip_venv
    mkdir -p "$GPU_RUN_DIR"
    local LOG="${GPU_RUN_DIR}/${NAME}.log" PIDFILE="${GPU_RUN_DIR}/${NAME}.pid"

    PATH="${GPU_VENV_DIR}/bin:${PATH}" \
        nohup bash -c "${BM_CMD} 2>&1; echo '=== Benchmark Complete ==='" >"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    disown

    echo "Process '$NAME' running (pid $(cat "$PIDFILE"))."
    echo ""
    echo "Monitor: tail -f $LOG"
    echo "Stop:    kill \$(cat $PIDFILE)"
}

# ── Launch ──
if [[ "$DEVICE" == "gpu" ]]; then
    echo "Launching natively (pip)..."
    launch_gpu_native
else
    echo "Launching on ${RUNTIME}..."
    if [[ "$RUNTIME" == "k3s" ]]; then launch_k3s; else launch_docker; fi
fi
echo ""
echo "Pair with power monitor: $(dirname "$0")/pt_mon.sh"
