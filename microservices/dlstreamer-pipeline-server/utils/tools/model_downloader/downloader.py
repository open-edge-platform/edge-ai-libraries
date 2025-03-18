#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import sys
import os
import shutil
import subprocess
import tempfile
import shlex
from glob import glob
from collections import namedtuple
import requests
import yaml
from jsonschema import Draft7Validator, FormatChecker
from mdt_schema import model_list_schema
from model_index_schema import model_index_schema

# Elements of OMZ_PATHS must all exist for detection/validity of the "base_type"
OMZ_PATHS = {
    "dlstreamer_devel": {
        "MODEL_DOWNLOADER_PATH": "/usr/local/bin/omz_downloader",
        "MODEL_CONVERTER_PATH": "/usr/local/bin/omz_converter",
        "MODEL_OPTIMIZER_PATH": "/usr/local/bin/mo"
    },
    "openvino_data_dev": {
        "MODEL_DOWNLOADER_PATH": "/opt/intel/openvino/deployment_tools/open_model_zoo/tools/downloader/downloader.py",
        "MODEL_CONVERTER_PATH": "/opt/intel/openvino/deployment_tools/open_model_zoo/tools/downloader/converter.py",
        "MODEL_OPTIMIZER_PATH": "/opt/intel/openvino/deployment_tools/model_optimizer/mo.py",
        "DLSTREAMER_VERSION_FILE": "/opt/intel/openvino/data_processing/dl_streamer/version.txt"
    }
}
SAMPLES_ROOT = "/opt/intel/dlstreamer/samples"
MODEL_INDEX_FILE = "model_index.yaml"
MODEL_PROC_SEARCH_PATH = "/opt/intel/openvino/data_processing/dl_streamer/samples/model_proc/**/{0}.json"
# Pointer to Intel(R) Deep Learning Streamer (Intel(R) DL Streamer) repository
DL_STREAMER_REPO_ROOT = "https://raw.githubusercontent.com/openvinotoolkit/dlstreamer_gst"

MODEL_LIST_EXPECTED_SCHEMA = "\n- model(Required): mobilenet-ssd\n \
 alias(Optional): object_detection\n \
 version(Optional): 1\n \
 precision(Optional): [FP16,FP32]"

MODEL_INDEX_EXPECTED_SCHEMA = '{<model name>: {model-proc (optional): <value>,\
 labels-file (optional) : <value>}}'

def get_base_image_type():
    valid_types = list(OMZ_PATHS.keys())
    for base_type, path_dict in OMZ_PATHS.items():
        for _, file_path in path_dict.items():
            if not os.path.exists(file_path):
                print("Filespec show this OMZ image is not base_type {}".format(base_type))
                valid_types.remove(base_type)
                break
    if not valid_types:
        return None
    if len(valid_types) > 1:
        print("ERROR: Paths are not sufficiently distinct to discover base_type!")
        return None
    return valid_types[0]

def _validate_schema(data, schema):
    try:
        validator = Draft7Validator(schema, format_checker=FormatChecker())
        validator.validate(data)
    except Exception as error:
        print("Yaml input schema validation error.")
        print(error)
        sys.exit(1)


def _load_yaml_data(file_path, schema, expected_schema):
    data = None
    try:
        with open(file_path) as file:
            data = yaml.safe_load(file)
    except Exception:
        print("Exception while loading yaml file. File could be malformed.")
        print("Please make sure model list file is in correct yml file format.")
        print("Expected Schema: {}".format(expected_schema))

    if data is None:
        sys.exit(1)
    else:
        _validate_schema(data, schema)
    return data


def _find_downloaded_model(model_name, download_dir):
    for root, directories, _ in os.walk(download_dir):
        if model_name in directories:
            return os.path.abspath(os.path.join(root, model_name))
    return None

def _copy_datadev_model_proc(base_type, target_dir, model_name, dl_streamer_version, version_file):
    result = None

    with open(version_file) as local_version:
        version = "v" + local_version.readline()
        if version.startswith(dl_streamer_version):
            model_proc = None
            search_path = MODEL_PROC_SEARCH_PATH.format(
                model_name)
            for model_proc in glob(search_path, recursive=True):
                break
            if model_proc:
                try:
                    result = shutil.copy(model_proc, os.path.join(target_dir, "{}.json".format(model_name)))
                    print("Copied model_proc to: {}".format(result))
                except PermissionError:
                    print("Permission denied copying model_proc")
                except Exception as error:
                    print("Unexpected error: {}".format(error))
    return result

def _download_model_proc(base_type, target_dir, model_name, dl_streamer_version):
    url = "{0}/{1}/samples/model_proc/{2}.json".format(DL_STREAMER_REPO_ROOT, dl_streamer_version, model_name
    )
    response = requests.get(url)
    with tempfile.TemporaryDirectory() as temp_dir:
        if response.status_code == 200:
            with open(
                    "{0}/{1}.json".format(temp_dir, model_name), "wb"
            ) as out_file:
                out_file.write(response.content)
            print(
                "Downloaded {0} model-proc file from Intel(R) DL Streamer repository".format(
                    model_name
                )
            )
            model_proc = os.path.abspath(
                "{0}/{1}.json".format(temp_dir, model_name)
            )
            shutil.move(model_proc, os.path.join(target_dir, "{}.json".format(model_name)))
        else:
            print("WARNING: model-proc not found in Intel(R) DL Streamer repository!")


def _create_convert_command(base_type, model_name, output_dir, precisions):
    if precisions:
        cmd = "python3 {0} -d {3} --name {1} --precisions {2} -o {3} --mo {4}"
        return shlex.split(
            cmd.format(
                OMZ_PATHS[base_type]["MODEL_CONVERTER_PATH"],
                model_name,
                ",".join(map(str, precisions)),
                output_dir,
                OMZ_PATHS[base_type]["MODEL_OPTIMIZER_PATH"],
            )
        )
    cmd = "python3 {0} -d {2} --name {1} -o {2} --mo {3}"
    return shlex.split(
        cmd.format(OMZ_PATHS[base_type]["MODEL_CONVERTER_PATH"], model_name, output_dir,
                   OMZ_PATHS[base_type]["MODEL_OPTIMIZER_PATH"])
    )


def _create_download_command(base_type, model_name, output_dir, precisions):
    if precisions:
        cmd = "python3 {0} --name {1} --precisions {2} -o {3}"
        return shlex.split(
            cmd.format(
                OMZ_PATHS[base_type]["MODEL_DOWNLOADER_PATH"],
                model_name,
                ",".join(map(str, precisions)),
                output_dir,
            )
        )
    cmd = "python3 {0} --name {1} -o {2}"
    return shlex.split(cmd.format(OMZ_PATHS[base_type]["MODEL_DOWNLOADER_PATH"], model_name, output_dir))


def _run_command(command, model_name, step):
    print(" ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print("Error occured while {0} {1} model.".format(step, model_name))
        print("Please remove from input yml file and try again.")
        sys.exit(1)


def _download_model(base_type, model_name, output_dir, precisions):
    command = _create_download_command(base_type, model_name, output_dir, precisions)
    _run_command(command, model_name, "downloading")


def _convert_model(base_type, model_name, output_dir, precisions):
    command = _create_convert_command(base_type, model_name, output_dir, precisions)
    _run_command(command, model_name, "converting")


def _get_model_properties(model, model_list_path, target_root):
    result = model
    if not isinstance(model, dict):
        result = {}
        result["model"] = model
    result.setdefault("alias", result["model"])
    result.setdefault("version", 1)
    result.setdefault("precision", None)
    result.setdefault("model-proc", None)
    result.setdefault("labels", None)
    result.setdefault("labels-file", None)
    if result["model-proc"]:
        result["model-proc"] = os.path.abspath(
            os.path.join(os.path.dirname(model_list_path), result["model-proc"])
        )
    if result["labels-file"]:
        result["labels-file"] = os.path.abspath(
            os.path.join(os.path.dirname(model_list_path),
                         result["labels-file"])
    )
    result["target-dir"] = os.path.join(target_root,
                                        result["alias"],
                                        str(result["version"]))
    return result

def _find_model_property_value(model_name, model_key, model_proc_dict, samples_root):
    model_value = None
    model_data = model_proc_dict.get(model_name, {})
    if model_key in model_data:
        model_value = os.path.join(samples_root, model_data[model_key])
        print("{} : {} for model {} per model_index.yaml".format(
            model_key, model_value, model_name))
    if model_value is None:
        print("No {} for model {} in the image per model_index.yaml".format(
            model_key, model_name))

    return model_value

def _download_and_convert_model(base_type, model_properties):
    model_name = model_properties["model"]
    precision = model_properties["precision"]
    target_dir = model_properties["target-dir"]

    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)

    with tempfile.TemporaryDirectory() as output_dir:
        _download_model(base_type, model_name, output_dir, precision)
        _convert_model(base_type, model_name, output_dir, precision)
        downloaded_model_path = _find_downloaded_model(model_name, output_dir)
        for path in os.listdir(downloaded_model_path):
            source = os.path.join(downloaded_model_path, path)
            target = os.path.join(target_dir, path)
            if os.path.isdir(source):
                shutil.move(source, target)


def _handle_model_files(base_type, model_properties, model_proc_dict, dl_streamer_version):
    model_name = model_properties["model"]
    model_proc = model_properties["model-proc"]
    labels = model_properties["labels"]
    target_dir = model_properties["target-dir"]

    if base_type == "openvino_data_dev":
        version_file = OMZ_PATHS[base_type]["DLSTREAMER_VERSION_FILE"]
        if not model_proc and _copy_datadev_model_proc(base_type,
            target_dir, model_name, dl_streamer_version, version_file) is None:
            _download_model_proc(base_type, target_dir, model_name, dl_streamer_version)
    else:
        if not model_proc:
            model_proc = _find_model_property_value(model_name, "model-proc", model_proc_dict, SAMPLES_ROOT)
        if not labels:
            labels = _find_model_property_value(model_name, "labels-file", model_proc_dict, SAMPLES_ROOT)

    collateral = namedtuple('Collateral', ['name', 'value'])
    model_proc_tuple = collateral("model-proc", model_proc)
    labels_tuple = collateral("labels-file", labels)
    for item in [model_proc_tuple, labels_tuple]:
        if item.value:
            if os.path.isfile(item.value):
                shutil.copy(item.value, target_dir)
            else:
                print("Error, {} {} specified but not found".format(item.name, item.value))
                sys.exit(1)

def find_model_index(samples_root):
    model_index_search_path = samples_root + "/**/" + MODEL_INDEX_FILE
    model_index_pathfile = None
    for model_index_pathfile in glob(model_index_search_path, recursive=True):
        break
    return model_index_pathfile

def download_and_convert_models(
        base_type, model_list_path, output_dir, force, dl_streamer_version
):
    global SAMPLES_ROOT
    model_list = _load_yaml_data(model_list_path, model_list_schema, MODEL_LIST_EXPECTED_SCHEMA)
    model_proc_dict = None
    if base_type == "dlstreamer_devel":
        model_index_file = find_model_index(SAMPLES_ROOT)
        if model_index_file:
            print("Found model index: {}".format(model_index_file))
            SAMPLES_ROOT, _ = os.path.split(model_index_file)
            model_proc_dict = _load_yaml_data(
                model_index_file, model_index_schema, MODEL_INDEX_EXPECTED_SCHEMA
            )
    target_root = os.path.join(output_dir, "models")
    os.makedirs(target_root, exist_ok=True)

    for model in model_list:
        model_properties = _get_model_properties(
            model, model_list_path, target_root)
        target_dir = model_properties["target-dir"]
        if (not force) and (os.path.isdir(target_dir)):
            print("Model Directory {0} Exists - Skipping".format(target_dir))
            continue
        _download_and_convert_model(base_type, model_properties)
        _handle_model_files(base_type, model_properties, model_proc_dict, dl_streamer_version)
