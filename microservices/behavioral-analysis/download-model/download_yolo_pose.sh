#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# YOLO26n Pose Model Download Script
# Downloads and converts YOLO26n Pose model to OpenVINO format
# 
# Usage:
#   ./download_yolo_pose.sh [OPTIONS]
#
# Options:
#   --model-name NAME       Model variant (default: yolo26n-pose)
#                          Options: yolo26n-pose, yolo26s-pose, yolo26m-pose, etc.
#   --help                 Show this help message
#
# Examples:
#   ./download_yolo_pose.sh                    # Download default yolo26n-pose
#   ./download_yolo_pose.sh --model-name yolo26s-pose

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODELS_DIR="${PROJECT_ROOT}/models/yolo_models"
YOLO_VENV_DIR="${SCRIPT_DIR}/yolo-venv"
YOLO_MODEL_NAME="${YOLO_MODEL_NAME:-yolo26n-pose}"

###############################################
# CONFIGURATION - Parse command line arguments
###############################################
while [[ $# -gt 0 ]]; do
    case $1 in
        --model-name)
            YOLO_MODEL_NAME="$2"
            shift 2
            ;;
        --help)
            echo "YOLO26n Pose Model Download Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --model-name NAME    Model variant (default: yolo26n-pose)"
            echo "  --help               Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # Download default yolo26n-pose"
            echo "  $0 --model-name yolo26s-pose    # Download yolo26s-pose"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

###############################################
# COLORS for output
###############################################
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

###############################################
# HELPER FUNCTIONS
###############################################

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_step() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        print_error "$1 is not installed"
        return 1
    fi
    return 0
}

###############################################
# VALIDATION
###############################################

print_header "YOLO26n Pose Model Download & Conversion"

echo -e "Model Configuration:"
echo -e "  Model Name:    ${YOLO_MODEL_NAME}"
echo -e "  Models Dir:    ${MODELS_DIR}"
echo -e "  VEnv Dir:      ${YOLO_VENV_DIR}"
echo ""

# Check prerequisites
print_step "Checking prerequisites..."

if ! check_command python3; then
    print_error "Python 3 is required but not installed"
    exit 1
fi
print_success "python3 found"

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
print_success "Python version: ${PYTHON_VERSION}"

###############################################
# PYTHON VIRTUAL ENVIRONMENT SETUP
###############################################

print_step "Setting up Python virtual environment..."

print_step "Ensuring model output directory exists..."
mkdir -p "${MODELS_DIR}"
print_success "Model output directory ready: ${MODELS_DIR}"

if [ -d "${YOLO_VENV_DIR}" ] && [ -f "${YOLO_VENV_DIR}/bin/pip" ]; then
    print_warning "Virtual environment already exists (${YOLO_VENV_DIR})"
    print_step "Reusing existing virtual environment..."
else
    print_step "Creating new virtual environment..."
    python3 -m venv "${YOLO_VENV_DIR}" --clear
    print_success "Virtual environment created"
fi

# Activate virtual environment
print_step "Activating virtual environment..."
source "${YOLO_VENV_DIR}/bin/activate"
print_success "Virtual environment activated"

###############################################
# DEPENDENCIES INSTALLATION
###############################################

print_step "Installing dependencies..."

# Upgrade pip
print_step "  [1/4] Upgrading pip..."
python -m pip install -q --upgrade pip
print_success "  pip upgraded"

# Install PyTorch CPU version
print_step "  [2/4] Installing PyTorch (CPU)..."
python -m pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
if [ $? -eq 0 ]; then
    print_success "  PyTorch installed"
else
    print_error "  Failed to install PyTorch"
    deactivate 2>/dev/null || true
    exit 1
fi

# Install Ultralytics
print_step "  [3/4] Installing Ultralytics..."
python -m pip install -q ultralytics
if [ $? -eq 0 ]; then
    print_success "  Ultralytics installed"
else
    print_error "  Failed to install Ultralytics"
    deactivate 2>/dev/null || true
    exit 1
fi

# Install OpenVINO
print_step "  [4/4] Installing OpenVINO..."
python -m pip install -q openvino
if [ $? -eq 0 ]; then
    print_success "  OpenVINO installed"
else
    print_error "  Failed to install OpenVINO"
    deactivate 2>/dev/null || true
    exit 1
fi

print_success "All dependencies installed"

###############################################
# CREATE PYTHON DOWNLOAD SCRIPT
###############################################

print_step "Creating YOLO model download script..."

DOWNLOAD_SCRIPT="${SCRIPT_DIR}/download_yolo_pose.py"
LEGACY_DOWNLOAD_SCRIPT="${MODELS_DIR}/download_yolo_pose.py"

if [ -f "${LEGACY_DOWNLOAD_SCRIPT}" ]; then
    rm -f "${LEGACY_DOWNLOAD_SCRIPT}"
    print_success "Removed stale script from model directory"
fi

cat > "${DOWNLOAD_SCRIPT}" << 'PYEOF'
import os
import shutil
from pathlib import Path
from ultralytics import YOLO
import sys

# Configuration
YOLO_MODEL_NAME = os.environ.get('YOLO_MODEL_NAME', 'yolo26n-pose')
models_dir = Path(os.environ.get('YOLO_MODELS_DIR', '.'))

model_pt = models_dir / f"{YOLO_MODEL_NAME}.pt"
export_dir = models_dir / f"{YOLO_MODEL_NAME}_openvino_model"
target_dir = models_dir / YOLO_MODEL_NAME

print("=" * 60)
print(f"YOLO Pose Model Download & Conversion: {YOLO_MODEL_NAME}")
print("=" * 60)

# Step 1: Download base weights from Ultralytics
if not model_pt.exists():
    print(f"\n[1/4] Downloading {YOLO_MODEL_NAME}.pt ...")
    print(f"      Model: Ultralytics YOLO Pose")
    print(f"      Target: OpenVINO format for edge deployment")
    try:
        YOLO(f"{YOLO_MODEL_NAME}.pt")
        print(f"✓ Downloaded: {model_pt}")
    except Exception as e:
        print(f"✗ Download failed: {e}")
        sys.exit(1)
else:
    print(f"\n[1/4] {YOLO_MODEL_NAME}.pt already exists (skipping download)")

# Step 2: Export to OpenVINO FP32 format
print(f"\n[2/4] Converting to OpenVINO FP32 ...")
if not export_dir.exists() and not target_dir.exists():
    try:
        model = YOLO(str(model_pt))
        model.export(format="openvino", half=False)
        print(f"✓ Conversion complete: {export_dir}")
    except Exception as e:
        print(f"✗ Conversion failed: {e}")
        sys.exit(1)
else:
    print(f"✓ OpenVINO export already exists (skipping conversion)")

# Step 3: Extract and organize .xml and .bin files
print(f"\n[3/4] Organizing model files ...")
if export_dir.exists():
    target_dir.mkdir(parents=True, exist_ok=True)
    
    for ext in ("*.xml", "*.bin"):
        for f in export_dir.glob(ext):
            dest = target_dir / f"{YOLO_MODEL_NAME}{f.suffix}"
            shutil.move(str(f), str(dest))
            print(f"  ✓ {f.name} → {dest.name}")
    
    # Clean up temporary export directory
    shutil.rmtree(str(export_dir))
    print(f"✓ Cleaned up temporary directories")

# Step 4: Remove PyTorch weights (no longer needed)
print(f"\n[4/4] Cleanup ...")
if model_pt.exists():
    model_pt.unlink()
    print(f"✓ Removed {model_pt.name}")

print("\n" + "=" * 60)
print("✓ YOLO26n Pose Model Ready for OpenVINO!")
print("=" * 60)
print(f"\nModel Location: {target_dir}")
print(f"  ├─ {target_dir / f'{YOLO_MODEL_NAME}.xml'}  (Model structure)")
print(f"  └─ {target_dir / f'{YOLO_MODEL_NAME}.bin'}  (Model weights)")
print(f"\nModel Specifications:")
print(f"  ├─ Format: OpenVINO Intermediate Representation (IR)")
print(f"  ├─ Precision: FP32 (full floating-point)")
print(f"  ├─ Task: Pose Estimation")
print(f"  └─ Target: Behavioral analysis for activity detection")
PYEOF

print_success "Download script created"

###############################################
# DOWNLOAD AND CONVERT YOLO MODEL
###############################################

print_step "Executing YOLO model download..."

export YOLO_MODEL_NAME="${YOLO_MODEL_NAME}"
export YOLO_MODELS_DIR="${MODELS_DIR}"

if python "${DOWNLOAD_SCRIPT}"; then
    print_success "YOLO model download completed successfully"
else
    print_error "YOLO model download failed"
    deactivate 2>/dev/null || true
    exit 1
fi

###############################################
# FINAL VERIFICATION
###############################################

print_step "Verifying model files..."

MODEL_DIR="${MODELS_DIR}/${YOLO_MODEL_NAME}"
XML_FILE="${MODEL_DIR}/${YOLO_MODEL_NAME}.xml"
BIN_FILE="${MODEL_DIR}/${YOLO_MODEL_NAME}.bin"

if [ -f "${XML_FILE}" ] && [ -f "${BIN_FILE}" ]; then
    XML_SIZE=$(du -h "${XML_FILE}" | cut -f1)
    BIN_SIZE=$(du -h "${BIN_FILE}" | cut -f1)
    print_success "Model files verified"
    echo ""
    echo -e "  ${BLUE}File Sizes:${NC}"
    echo -e "    ${GREEN}✓${NC} ${XML_FILE##*/} (${XML_SIZE})"
    echo -e "    ${GREEN}✓${NC} ${BIN_FILE##*/} (${BIN_SIZE})"
else
    print_error "Model files not found"
    print_error "Expected:"
    print_error "  ${XML_FILE}"
    print_error "  ${BIN_FILE}"
    deactivate 2>/dev/null || true
    exit 1
fi

###############################################
# DEACTIVATE VENV AND SUMMARY
###############################################

print_step "Deactivating virtual environment..."
deactivate 2>/dev/null || true
print_success "Virtual environment deactivated"

print_header "✓ Setup Complete!"

echo ""
echo -e "  ${GREEN}YOLO26n Pose Model Ready for OpenVINO${NC}"
echo ""
echo -e "  ${BLUE}Model Location:${NC}"
echo -e "    ${MODEL_DIR}"
echo ""
echo -e "  ${BLUE}To reactivate the virtual environment:${NC}"
echo -e "    source ${YOLO_VENV_DIR}/bin/activate"
echo ""
echo -e "  ${BLUE}To run inference with OpenVINO:${NC}"
echo -e "    • Use the .xml and .bin files in: ${MODEL_DIR}"
echo -e "    • Deploy with OpenVINO Model Server (OVMS)"
echo -e "    • Integrate into Suspicious Activity Detection pipeline"
echo ""
echo -e "  ${BLUE}Documentation:${NC}"
echo -e "    • Model Format: OpenVINO Intermediate Representation (IR)"
echo -e "    • Precision: FP32 (full floating-point, ~100 MB)"
echo -e "    • Task: Pose Estimation for behavioral analysis"
echo ""
