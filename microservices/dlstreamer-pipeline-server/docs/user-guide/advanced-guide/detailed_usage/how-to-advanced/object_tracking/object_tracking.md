# Object tracking with UDF

- [Object tracking](#object-tracking)
- [Usage](#usage)
- [Recommendations](#recommendations)
- [Known Issues](#known-issues)

## Pre-requisites
Before proceeding, make sure you understand how to run pipelines that include the UDFLoader element. Refer to this [guide](../../../../how-to-run-udf-pipelines.md) for more information.

## Object tracking
Object tracking is supported by DL Streamer through `gvatrack` element which assigns ids to each uniquely identified objects. It is typically inserted into a video pipeline after `gvadetect` element. 

There are several tracking types supported, for example, short-term-imageless, zero-term, zero-term-imageless. By default, zero-term tracking is enabled which requires object detection to be run on every frame. 

More details object tracking, tracking types, performance considerations, examples can be found [here](https://dlstreamer.github.io/dev_guide/object_tracking.html).


## Usage

Note: By default, tracking is disabled. 

To enable object tracking in a video pipeline that has a UDFLoader element, two elements `gvapython` and `gvatrack` need to be inserted after the `udfloader` element in the pipeline. When tracking is enabled, the metadata will include the object ids starting from sequentially from `1` for each detection. 

1. `gvapython` element adds detected ROIs to video frame. This is required by the tracking element to assign object IDs. 
2. `gvatrack` adds tracking info.

To disable tracking, the above elements (if present) following the `udfloader` element need to be removed from the pipeline. When tracking is disabled, the metadata will include the object id as `None` for each detection.

Here is an example for enabling tracking for Pallet Defect Detection pipeline that uses Geti UDF. In Geti UDF, `metadata_converter` should be set to `geti_to_dcaas`.
  ```bash
  "pipeline": "multifilesrc loop=TRUE stop-index=0 location=/home/pipeline-server/resources/videos/warehouse.avi name=source ! h264parse ! decodebin ! queue max-size-buffers=10 ! videoconvert ! video/x-raw,format=RGB ! udfloader name=udfloader ! gvapython class=AddDetectionRoi function=process module=/home/pipeline-server/gvapython/detection/add_roi.py name=add_roi ! gvatrack tracking-type=short-term-imageless ! appsink name=destination",
  ```

  ```bash
     "udfs": {
        "udfloader": [
          {
            "name": "python.geti_udf.geti_udf",
            "type": "python",
            "device": "CPU",
            "visualize": "true",
            "deployment": "./resources/models/geti/pallet_defect_detection/deployment",
            "metadata_converter": "geti_to_dcaas"
          }
        ]
      }
  ```

Specific metadata format is expected out of the UDF for it work with the gvapython that adds ROIs.

## Recommendations
- Tracking accuracy is reliant on model's accuracy in detecting objects. For skipped detections, other tracking types like short-term-imageless may be explored which does not expect detection on every frame. 

- When running multiple pipelines with tracking enabled, the object ids would still sequentially start from 1 for each pipeline. It can be coupled with either pipeline tag or unique published topic identifying results associated with a specific pipeline. 

## Known Issues
Currently, visualizer does not show the object IDs along with the overlayed detection/labels.
