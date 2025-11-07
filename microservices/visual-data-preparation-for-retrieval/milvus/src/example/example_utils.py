# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from moviepy.editor import VideoFileClip, ImageSequenceClip
import os
import subprocess
import sys
from pathlib import Path
import shutil
import argparse

DAVIS_SUBSET_CATEGORIES = ["car-race", "deer", "guitar-violin", "gym", "helicopter", "carousel", "monkeys-trees", "golf", "rollercoaster", "horsejump-stick", "planes-crossing", "tractor"]


def images_to_video(image_folder: str, video_name: str, fps: int = 24) -> None:
    image_files = [os.path.join(image_folder, f) for f in sorted(os.listdir(image_folder))
                   if f.endswith((".png", ".jpg", ".jpeg"))]
    clip = ImageSequenceClip(image_files, fps=fps)
    clip.write_videofile(video_name, codec='libx264')

def process_subfolder(path: str, output_dir: str, skip_num: int, is_image: bool) -> None:
    path = Path(path)
    counter = 0
    name = os.path.basename(path)
    if is_image:
        print(path)
        for f in sorted(path.rglob('*.jpg')):
            if counter % (skip_num + 1) == 0:
                destination_image_path = os.path.join(f'{output_dir}', name + "_" + os.path.basename(f))
                shutil.copy2(f, destination_image_path)
            counter += 1
    else:
        images_to_video(path, f"{output_dir}/{path.name}.mp4", 24)

def download_dataset(dataset_name: str, dataset_path: str) -> None:
    command = ["echo", "Dataset download command not implemented"]
    if dataset_name == "DAVIS":
        if os.path.exists(os.path.join(dataset_path, "DAVIS-2017-test-dev-480p.zip")):
            print(f"Dataset zip file already exists at {dataset_path}. Skipping download.")
            return
        if not os.path.exists(dataset_path):
            os.makedirs(dataset_path)
        command = [
            "curl",
            "--retry", "5",  # Retry up to 5 times if the download fails
            "--max-time", "30",  # Set a timeout of 30 seconds for each attempt
            "--continue-at", "-",  # Resume partially downloaded files
            "--insecure",  # Skip SSL certificate validation (if necessary)
            "-o", os.path.join(dataset_path, "DAVIS-2017-test-dev-480p.zip"),  # Specify output file name
            "https://data.vision.ee.ethz.ch/csergi/share/davis/DAVIS-2017-test-dev-480p.zip"
        ]
    else:
        print(f"Unsupported dataset name: {dataset_name}")
        raise ValueError(f"Unsupported dataset name: {dataset_name}")

    try:
        print(f"Downloading {dataset_name} to {dataset_path}")
        result = subprocess.run(command, capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr) 
    except subprocess.CalledProcessError as e:
        print(f"Command failed with return code {e.returncode}")
        print(f"Error output: {e.stderr}")

def process_davis_dataset(dataset_path: str, skip_num: int, ratio: float, check_zip: bool = True) -> None:
    # unzip the dataset if not already unzipped
    zip_path = os.path.join(dataset_path, "DAVIS-2017-test-dev-480p.zip")
    if check_zip and not os.path.exists(zip_path):
        print(f"Dataset zip file not found at {zip_path}. Please download it first.")
        return
    if not os.path.exists(os.path.join(dataset_path, "DAVIS")):
        print(f"Unzipping dataset to {dataset_path}")
        subprocess.run(["unzip", zip_path, "-d", dataset_path], check=True)
    dataset_path = os.path.join(dataset_path, "DAVIS")
    dst_dataset_path = os.path.join(dataset_path, "subset")
    os.makedirs(dst_dataset_path, exist_ok=True)

    cut_point = len(DAVIS_SUBSET_CATEGORIES) * ratio  # 50% for images, 50% for videos
    cnt = 0

    for category in DAVIS_SUBSET_CATEGORIES:
        category_path = os.path.join(dataset_path, "JPEGImages", "480p", category)
        is_image = cnt < cut_point
        if os.path.exists(category_path):
            process_subfolder(category_path, dst_dataset_path, skip_num=skip_num, is_image=is_image)
            print(f"Processed {category_path} to {dst_dataset_path}")
        else:
            print(f"Category {category} not found in {dataset_path}")
        cnt += 1


def process_dataset(dataset_name: str, dataset_path: str, skip_num: int, ratio: float) -> None:
    download_dataset(dataset_name, dataset_path)
    if dataset_name == "DAVIS":
        process_davis_dataset(dataset_path, skip_num, ratio)
        return
    else:
        print(f"Unsupported dataset name: {dataset_name}")
        raise ValueError(f"Unsupported dataset name: {dataset_name}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser("Prepare dataset for building index", add_help=True)
    parser.add_argument('-d', '--dataset', default='DAVIS', help='Name of the dataset')
    parser.add_argument('-p', '--path', default='/home/user/data/', help='Path to the dataset')
    parser.add_argument('-s', '--skip_num', default='19', type=int, help='The number of frames skipped for the images. Suitable to datasets with images extracted from videos')
    parser.add_argument('-r', '--ratio', default='0.5', type=float, help='The ratio of splitting dataset into images and videos as images/total')

    args = parser.parse_args()

    process_dataset(args.dataset, args.path, args.skip_num, args.ratio)