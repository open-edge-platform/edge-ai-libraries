# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from ultralytics import YOLO
import openvino, shutil, os
import argparse

def convert_model(model_name, model_type, output_dir):
    pt_weights_file = model_name + '.pt'
    model = YOLO(pt_weights_file)
    model.info()

    fp16_output_dir = os.path.join(output_dir, "FP16")
    fp32_output_dir = os.path.join(output_dir, "FP32")

    os.makedirs(fp16_output_dir, exist_ok=True)
    os.makedirs(fp32_output_dir, exist_ok=True)

    converted_path = model.export(format='openvino')
    converted_model = converted_path + '/' + model_name + '.xml'

    core = openvino.Core()
    ov_model = core.read_model(model=converted_model)
    
    if model_type in ["YOLOv8-SEG", "yolo_v11_seg"]:
        ov_model.output(0).set_names({"boxes"})
        ov_model.output(1).set_names({"masks"})
    ov_model.set_rt_info(model_type, ['model_info', 'model_type'])

    # Save models in FP32 and FP16 formats
    openvino.save_model(ov_model, os.path.join(fp32_output_dir, model_name + '.xml'), compress_to_fp16=False)
    openvino.save_model(ov_model, os.path.join(fp16_output_dir, model_name + '.xml'), compress_to_fp16=True)

    # Clean up temporary files
    try:
        if os.path.exists(converted_path):
            shutil.rmtree(converted_path)
        if os.path.exists(pt_weights_file):
            os.remove(pt_weights_file)
    except Exception as e:
        print(f"Warning: Failed to clean up temporary files: {e}")
    
    print(f"Model converted successfully and saved to {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="Convert YOLO models to OpenVINO IR format")
    parser.add_argument("--model-name", type=str, default='yolov8l-worldv2', 
                        help="Name of the model (without extension, e.g., 'yolov8l-worldv2')")
    parser.add_argument("--model-type", type=str, default='yolo_v8', 
                        help="Type of model (e.g., 'yolo_v8', 'YOLOv8-SEG')")
    parser.add_argument("--output-dir", type=str, default='ov_models/yoloworld/v2', 
                        help="Directory to save the converted models")
    
    args = parser.parse_args()
    
    convert_model(args.model_name, args.model_type, args.output_dir)

if __name__ == "__main__":
    main()