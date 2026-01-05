# Cross stream batching

Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server) supports grouping multiple
frames in single batch during model processing. `batch-size` is an optional parameter to be used
which specifies the number of input frames grouped together in a single batch.

For multi stream pipelines using same pipeline configuration, it is recommended to create a [shared inference element](./multistream-pipelines.md) by setting `model-instance-id` to a unique value along with `batch-size` for cross stream batching to occur across elements with same `model-instance-id`.

Below is an example that demonstrates cross stream batching, 4 frames at a time.

```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection batch-size=4 model-instance-id=1 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
```

Choosing the right batch size:

* `Real time applications`  Keep the batch-size small to minimize the latency. A larger batch size may cause the initial frames to wait until the batch is completely filled before the model begins processing. Also, large batch size means higher memory utilization
* `High throughput `  Keep the batch-size large to maximize the throughput. Some hardware are suited to process large number of frames in parallel, thus reducing overall time required to process all the frames.

> For optimal performance, set `batch-size` to an integer multiple of the stream count. Typically, setting `batch-size` equal to the number of streams (`batch-size=<number of streams>`) yields the best results.

> In a multi stream pipeline with a shared model instance, frames can be grouped into a single batch either from multiple pipelines or exclusively from one pipeline, depending on the timing of arrival of frames from the pipelines.

The following curl command can be used to start the pipeline -
``` sh
    curl http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
    "source": {
        "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
        "type": "uri"
    },
    "destination": {
        "metadata": {
            "type": "file",
            "path": "/tmp/results.jsonl",
            "format": "json-lines"
        },
        "frame": {
            "type": "rtsp",
            "path": "pallet-defect-detection"
        }
    },
    "parameters": {
        "detection-properties": {
            "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
            "device": "CPU"
        }
    }
}'
```

To verify the effect of `batch-size`, you can monitor the memory utilization of the Docker container using the `docker stats` command. As the `batch-size` increases, the memory utilization also increases due to the additional frames being processed in a single batch. Note that the exact statistics may vary based on the underlying hardware and system/pipeline configuration but the performance is expected to be similar to [DL Streamer](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/dev_guide/performance_guide.md#3-multi-stream-pipelines-with-single-ai-stage).

* docker stats with batch-size as 1, no of streams as 4
```sh
CONTAINER ID   NAME                         CPU %      MEM USAGE / LIMIT     MEM %     NET I/O         BLOCK I/O     PIDS
b69749537d3a   dlstreamer-pipeline-server   2283.24%   463.2MiB / 62.52GiB   0.72%     19.2kB / 10kB   0B / 3.29MB   101
```

* docker stats with batch-size as 4, no of streams as 4
```sh
CONTAINER ID   NAME                         CPU %      MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O   PIDS
04a4249217ba   dlstreamer-pipeline-server   2317.13%   782.4MiB / 62.52GiB   1.22%     10.1kB / 1.97kB   0B / 0B     102
```

* docker stats with batch-size as 8, no of streams as 4
```sh
CONTAINER ID   NAME                         CPU %      MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O   PIDS
d8023608aa07   dlstreamer-pipeline-server   2316.66%   1.181GiB / 62.52GiB   1.89%     11.2kB / 1.62kB   0B / 0B     102
```

* docker stats with batch-size as 16, no of streams as 4
```sh
CONTAINER ID   NAME                         CPU %      MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O   PIDS
a89844e28f7a   dlstreamer-pipeline-server   2254.41%   2.001GiB / 62.52GiB   3.20%     11.9kB / 2.22kB   0B / 0B     100
```
