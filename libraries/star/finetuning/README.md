<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# YOLO Fine-Tuning Module

A simple standalone repo for fine-tuning YOLOv8 models on custom datasets using the ultralytics library.

## Overview

This workflow includes two scripts:
- `finetune_det_model.py`: fine-tunes a pretrained YOLOv8 detector on your custom dataset, with all layers trainable and built-in augmentation/training defaults.
- `split_remap_yolo_dataset.py`: prepares data by splitting labels/images into train/val/test and remapping class IDs for your target taxonomy.

Together, they cover dataset preparation first, then model fine-tuning.

### Dependencies for Shared Scripts

For both `finetune_det_model.py` and `split_remap_yolo_dataset.py`, install packages from the project requirements file:

`requirements.txt`

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Basic Fine-Tuning

```bash
# Run with default settings
python finetune_det_model.py

# Or customize parameters
python -c "from finetune_det_model import train; train(
    model_path='../models/yolov8m.pt',
    data_yaml='data_nrl.yaml',
    total_epochs=100,
    imgsz=640,
    batch=128,
    device='0,1,2,3,4,5,6,7'
)"
```

## Function Reference

### `train()`

Main fine-tuning function.

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_path` | `../models/obj_det_models/yolov8m.pt` | Path to pre-trained YOLO model |
| `data_yaml` | `data_nrl.yaml` | Dataset configuration file |
| `total_epochs` | `100` | Number of training epochs |
| `imgsz` | `640` | Input image size (pixels) |
| `batch` | `128` | Batch size per GPU |
| `device` | `'0,1,2,3,4,5,6,7'` | GPU device IDs (comma-separated) |

**Example:**
```python
from finetune_det_model import train

train(
    model_path='models/yolov8m.pt',
    data_yaml='datasets/custom_data.yaml',
    total_epochs=50,
    imgsz=640,
    batch=64,
    device='0,1'  # Use GPUs 0 and 1
)
```

### Utility Functions

#### `_print_class_counts(data_yaml)`
Analyzes and displays the number of instances per class in training set.

```python
from finetune_det_model import _print_class_counts

_print_class_counts('data_nrl.yaml')
# Output:
# Training class instance counts:
#   0: person -> 5432
#   1: vehicle -> 3201
#   2: object -> 1543
```

## Dataset Setup (YOLO Format)

### Directory Structure

```
datasets/
└── custom_data/
    ├── images/
    │   ├── train/
    │   │   ├── img1.jpg
    │   │   ├── img2.jpg
    │   │   └── ...
    │   ├── val/
    │   └── test/
    └── labels/
        ├── train/
        │   ├── img1.txt
        │   ├── img2.txt
        │   └── ...
        ├── val/
        └── test/
```

### Label Format (YOLO)

Each image has a corresponding `.txt` file with one line per object:

```
<class_id> <x_center> <y_center> <width> <height>
```

**Example:**
```
0 0.5 0.5 0.3 0.4
1 0.2 0.7 0.15 0.25
```

All coordinates are **normalized to [0, 1]**.

### Data Configuration YAML

Create `data_nrl.yaml`:

```yaml
# Dataset root path
path: /path/to/custom_data

# Train, val, test image directories
train: images/train
val: images/val
test: images/test

# Number of classes
nc: 5

# Class names
names:
  0: Person
  1: Vehicle
  2: Aerial
  3: Vessel
  4: Bird 
```

## Training Configuration

The `train()` function uses these optimizations:

### Model Training
- **`freeze=0`** - Trains all layers (no freezing)
- **`lr0=0.001`** - Conservative learning rate for stability

### Data Augmentation
- **HSV augmentation**: `hsv_v=0.2` (slight brightness variation)
- **Geometric transforms**: Rotation ±5°, translation ±10%, scale 0.5-1.5x
- **Flipping**: 50% horizontal flip
- **Mosaic/Mixup**: 50% mosaic, 10% mixup
- **Erasing**: 20% cutout augmentation

### Performance Settings
- **Multi-GPU**: Distribute batch across GPUs
- **Workers**: 4 parallel data loaders
- **Caching**: Disabled (set to False)
- **Pretrained**: Uses ImageNet pre-trained weights

## Usage Examples

### Example 1: Fine-tune on Custom Dataset

```python
from finetune_det_model import train

# Fine-tune medium YOLOv8 for 100 epochs
train(
    model_path='yolov8m.pt',           # Or download automatically
    data_yaml='configs/my_dataset.yaml',
    total_epochs=100,
    imgsz=640,
    batch=64,
    device='0,1,2,3'                   # 4 GPUs
)
```

### Example 2: Fine-tune with Different Model Size

```python
from finetune_det_model import train

# Nano model for edge deployment
train(
    model_path='yolov8n.pt',
    data_yaml='data.yaml',
    total_epochs=50,
    batch=128,
    device='0'
)

# Or large model for best accuracy
train(
    model_path='yolov8l.pt',
    data_yaml='data.yaml',
    total_epochs=100,
    batch=32,
    device='0,1,2,3,4,5,6,7'
)
```

### Example 3: Single GPU Training

```python
from finetune_det_model import train

train(
    model_path='yolov8m.pt',
    data_yaml='data.yaml',
    total_epochs=50,
    batch=16,  # Smaller batch for single GPU
    device='0'
)
```

## Output

Training outputs are saved to `runs/detect/trainN/` (where N is auto-incremented):

```
runs/detect/train/
├── weights/
│   ├── best.pt          # Best model weights
│   ├── last.pt          # Last epoch weights
│   └── ...
├── results.csv          # Training metrics per epoch
├── results.png          # Training plots
├── confusion_matrix.png
└── val_batch*.jpg       # Sample validation images
```

## Hyperparameter Tuning

Common adjustments:

| Goal | Change |
|------|--------|
| Faster training | ↓ `total_epochs`, ↓ `imgsz`, ↑ `device` GPUs |
| Better accuracy | ↑ `total_epochs`, ↑ `imgsz`, ↓ `batch` |
| Less overfitting | ↓ `batch`, ↑ augmentation parameters |
| Faster inference | Use `yolov8n.pt` instead of `yolov8l.pt` |

## Environment Variables

```bash
# Use specific GPUs
export CUDA_VISIBLE_DEVICES=0,1,2,3

# Disable logging
export YOLOv5_VERBOSE=0
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Out of memory | Reduce `batch` size or `imgsz` |
| Slow training | Increase `device` GPUs or reduce `imgsz` |
| Labels not found | Check `images/` → `labels/` conversion (helper function handles this) |
| Poor accuracy | Increase `total_epochs`, check data quality, verify label format |
| Model path error | Use absolute path or download via `yolov8m.pt` (downloads automatically) |

## Model Variants

Pre-trained YOLO models available:

| Model | Speed | Accuracy | Parameters |
|-------|-------|----------|-----------|
| yolov8n | ⚡ Very Fast | Low | 3.2M |
| yolov8s | 🏃 Fast | Medium | 11.2M |
| yolov8m | 🚴 Balanced | High | 25.9M |
| yolov8l | 🐢 Slow | Very High | 63.4M |
| yolov8x | 🐢 Very Slow | Excellent | 107.1M |

## Class Distribution Analysis

View training class imbalance before training:

```python
from finetune_det_model import _print_class_counts

_print_class_counts('data.yaml')
```

This helps identify if certain classes are underrepresented and may need:
- More data collection
- Class weighting adjustments
- Augmentation tuning

## Export to OpenVINO INT8 (Quantized Model)

After fine-tuning, you can export the best model to **OpenVINO INT8** format using post-training quantization with calibration. This significantly reduces model size and speeds up inference on Intel hardware (CPU, iGPU, VPU).

### Export Command

```bash
yolo export \
    model=runs/detect/train/weights/best.pt \
    format=openvino \
    int8=True \
    data=data.yaml
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `model` | Path to your fine-tuned `.pt` weights (typically `best.pt`) |
| `format=openvino` | Exports to OpenVINO IR format (`.xml` + `.bin`) |
| `int8=True` | Enables INT8 quantization via calibration (requires `data`) |
| `data` | Dataset YAML used for calibration — a small subset of your training/val images is used to compute quantization ranges |

### Output

The exported model is saved alongside the `.pt` file:

```
runs/detect/train/weights/
└── best_openvino_model/
    ├── best.xml        # Model graph
    ├── best.bin        # Quantized weights
    └── metadata.yaml
```

### Notes

- The `data.yaml` file is **required** for INT8 calibration — it tells the exporter which images to sample for calibration statistics.
- Calibration typically uses ~100–300 representative images from the validation set.
- INT8 models run fastest on **Intel CPUs and iGPUs** with OpenVINO Runtime.
- For deployment, use the `best_openvino_model/` directory as the model path in your inference pipeline.

## References

- [Ultralytics YOLOv8 Docs](https://docs.ultralytics.com/)
- [YOLO Dataset Format](https://docs.ultralytics.com/datasets/detect/)
- [Training Arguments](https://docs.ultralytics.com/usage/cfg/)
- [YOLO Export to OpenVINO](https://docs.ultralytics.com/integrations/openvino/)


## Split Data for Training (Train/Val/Test + Class Remap)

Use `split_remap_yolo_dataset.py` to prepare a YOLO dataset from data by:
- splitting images/labels into `train`, `val`, and `test`
- remapping original class IDs to your target training classes

It expects YOLO-style source folders (`images/` and `labels/`) and writes a new dataset with:

```
<dst>/
  images/train, images/val, images/test
  labels/train, labels/val, labels/test
```

### Example command (with class-id remapping)

```bash
python split_remap_yolo_dataset.py \
    --src ../data/raw_yolo \
    --dst ../data/split_remap \
    --ratios 80,10,10 \
    --mapping 0:0,1:0,2:1,3:2,4:3 \
    --action copy \
    --unmapped drop \
    --seed 42
```

### What this example does

- `--ratios 80,10,10`: creates 80% train, 10% val, 10% test
- `--mapping 0:0,1:0,2:1,3:2,4:3`: merges old classes `0` and `1` into new class `0`, remaps others
- `--unmapped drop`: drops annotations whose class IDs are not in the mapping
- `--action copy`: copies files (safe default for preserving original data)

After this step, point your `data.yaml` (`path`, `train`, `val`, `test`, `names`) to `../data/split_remap` and run `finetune_det_model.py`.


