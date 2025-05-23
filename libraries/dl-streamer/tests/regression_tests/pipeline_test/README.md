# Regression test tool

## Requirements

You need Python 3.5 or later to run regression tests

In Linux you can install Python 3 like this:

    sudo apt-get install python3 python3-pip

Besides python, you need to install python packages from requriements.txt file:

    pip install -r requrements.txt

## Quick start

Now that python is installed and the environment is configured, you can start the tool. Run `python3 -m regression_test -h` from current directory to see the help.
To get started, you need several json files:

* Configuration file with **test sets** that contain **test cases**.
* A json file with the original ground truth for each test case to be compared with. **Important note for "video" and "audio":** The name of the file into which you will publish metadata must be the same as the name of the original ground truth file with which you want to compare.
* To specify ground truth for "video" and "audio" tests your pipeline should contain `gvametapublish file-path=...`, recommended pipeline: `gvametaconvert ! gvametapublish file-path=/path/to/groundtruth.json method=file file-format=json-lines`.
* For "watermark" you should use `dataset.groundtruth` in test configuration file

Example of regression test:

    python3 -m regression_test -c /path/to/config.json

More easer way is to launch `entry_point.sh` script which setup python required python packages and launch regression tool with specified parameters:

    ./entry_point.sh -c /path/to/config.json --force --xml-report /path/where/to/put/report.xml

## How to write config

To write your own config, you will need to specify several required keys:

* `test_sets` field with all the names of the test sets that you want to create in this config
* `dataset.groundtruth.base` key with path to folder with original ground truth json files
* `dataset.groundtruth` key for ground truth json file name
* `dataset.comparator_type` key for ground truth comparator. Possible values are ["video", "audio", "watermark"]. If not specified, "video" is used.
* `pipeline.template` key to describe template of pipelines that will run in the current test set

The `test_set_properties` field is optional. In it, you can declare general parameters of test sets, which will be substituted in the appropriate places during the generation of test cases.
Simple possible config file example:

```json
{
    "test_set_properties": {
        "pipeline.inference.model.name": "model_name",
        "dataset": "/path/to/media/file.mp4",
        "dataset.groundtruth.base": "/path/to/original/groundtruth/folder",
        "dataset.groundtruth": "dumped_metadata_file_name.json"
    },
    "test_sets": {
        "some_crazy_test_set": [
            ["pipeline.template", "filesrc location={dataset} ! decodebin ! video/x-raw ! gvadetect model={pipeline.inference.model.path} ! gvametaconvert format=json add-tensor-data=true ! gvametapublish file-path=/tmp/results/{dataset.groundtruth} method=file file-format=json-lines ! fakesink"]
        ]
    }
}
```

When using this test config, a test set from one test case with the pipeline below will be generated and launched:

    gst-launch filesrc location=/path/to/media/file.mp4 ! decodebin ! video/x-raw ! gvadetect model=/path/to/model_name.xml ! gvametaconvert format=json add-tensor-data=true ! gvametapublish file-path=/tmp/results/dumped_metadata_file_name.json method=file file-format=json-lines ! fakesink

After successful completion of the test case, the `/tmp/results/dumped_metadata_file_name.json` file with metadata will be compared with the original ground truth file with the same `dumped_metadata_file_name.json` name. It is expected that the original Groundtruth file will be located at `/path/to/original/groundtruth/folder` folder, which should be specified in `dataset.groundtruth.base` field.
### How to generate or update ground truth
`watermark`:

    `./generate_watermark_gt.sh`

This script does not have additional requirements.

`video` and `audio`: TBD
#### Using model-proc explorer
Regression test tool uses automatic model-proc path substitution. This means that in the config you should specify only model-proc file name in the test set properties and in the pipeline template use key with suffix ".model_proc/path". 
Example:

```json
{
    "test_set_properties": {
        "pipeline.inference.model.name": "model_name",
        "pipeline.inference.model.model_proc": "model-proc.json",
        "dataset": "/path/to/media/file.mp4",
        "dataset.groundtruth.base": "/path/to/original/groundtruth/folder",
        "dataset.groundtruth": "dumped_metadata_file_name.json"
    },
    "test_sets": {
        "some_crazy_test_set": [
            ["pipeline.template", "filesrc location={dataset} ! decodebin ! video/x-raw ! gvadetect model={pipeline.inference.model.path} model-proc={pipeline.inference.model.model_proc.path} ! gvametaconvert format=json add-tensor-data=true ! gvametapublish file-path=/tmp/results/{dataset.groundtruth} method=file file-format=json-lines ! fakesink"]
        ]
    }
}
``` 

### Features and Tags

`--tags` option run all tests with non-empty intersection with runner tags
`--features` some tests start only if list of runner features satisfies test required features, by default test require empty list of features 

### Platforms

In case you want to run the test case on specific platforms, you can specify the `platforms` field in the json config file. By default, if no platforms are specified, TC will run on all platforms. Otherwise, this TC will be launched if these platforms are found in the platform information. Platforms allow you to use the same configuration json file for different platforms with different results in GT. For example:

```json
{
    "test_sets": {
        "test_set_with_platforms": [
            [["platforms", "dataset.groundtruth"], [
                ["Ubuntu" "ubuntu_test_set_with_platforms.json"],
                ["CentOS", "centos_test_set_with_platforms.json"],
                [["Ubuntu-18.04", "Windows"], "ubuntu18_windows_test_set_with_platforms.json"],
            ]],
            ["pipeline.template", "filesrc location={dataset} ! decodebin ! video/x-raw ! gvadetect model={pipeline.inference.model.path} ! gvametaconvert format=json add-tensor-data=true ! gvametapublish file-path=/tmp/results/{dataset.groundtruth} method=file file-format=json-lines ! fakesink"]
        ]
    }
}
