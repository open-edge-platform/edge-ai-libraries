# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from ultralytics import YOLO
import openvino, sys, shutil, os
import argparse

def convert_model(model_name, model_type, output_dir):
    weights = model_name + '.pt'
    model = YOLO(weights)
    model.info()

    converted_path = model.export(format='openvino')
    converted_model = converted_path + '/' + model_name + '.xml'

    core = openvino.Core()

    ov_model = core.read_model(model=converted_model)
    if model_type in ["YOLOv8-SEG", "yolo_v11_seg"]:
        ov_model.output(0).set_names({"boxes"})
        ov_model.output(1).set_names({"masks"})
    ov_model.set_rt_info(model_type, ['model_info', 'model_type'])

    # Create output directories if they don't exist
    os.makedirs(os.path.join(output_dir, 'FP32'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'FP16'), exist_ok=True)

    # Save models in FP32 and FP16 formats
    openvino.save_model(ov_model, os.path.join(output_dir, 'FP32', model_name + '.xml'), compress_to_fp16=False)
    openvino.save_model(ov_model, os.path.join(output_dir, 'FP16', model_name + '.xml'), compress_to_fp16=True)

    # Clean up temporary files
    shutil.rmtree(converted_path)
    os.remove(f"{model_name}.pt")
    
    print(f"Model converted successfully and saved to {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="Convert YOLO models to OpenVINO IR format")
    parser.add_argument("--model-name", type=str, default='yolov8l-worldv2', 
                        help="Name of the model (without extension, e.g., 'yolov8l-worldv2')")
    parser.add_argument("--model-type", type=str, default='yolo_v8', 
                        help="Type of model (e.g., 'yolo_v8', 'YOLOv8-SEG')")
    parser.add_argument("--output-dir", type=str, default='ov_models/yoloworld', 
                        help="Directory to save the converted models")
    
    args = parser.parse_args()
    
    convert_model(args.model_name, args.model_type, args.output_dir)

if __name__ == "__main__":
    main()