# Cross stream batching

EVAM supports grouping multiple frames in single batch during model processing. `batch-size` is an optional parameter to be used which specifies the number of input frames grouped together in a single batch. In the below example, the model processes 4 frames at a time.

```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection batch-size=4 model-instance-id=1 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink",
```

Choosing the right batch size:

* `Real time applications`  Keep the batch-size small to minimize the latency. A larger batch size may cause the initial frames to wait until the batch is completely filled before the model begins processing. Also, large batch size means higher memory utilization
* `High throughput `  Keep the batch-size large to maximize the throughput. Some hardware are suited to process large number of frames in parallel, thus reducing overall time required to process all the frames.

`Note` In a multi stream pipeline with a shared model instance, frames can be grouped into a single batch either from multiple pipelines or exclusively from one pipeline, depending on the timing of arrival of frames from the pipelines.

To verify the effect of batch-size you can check the memory utilization of docker by using command `docker stats`. The memory utilization increases when we load multiple frames in one batch. The stats may vary depending on the underlying hardware. 

You can use the following curl command to start the pipeline - 
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

* docker stats with batch-size as 1, no of streams as 1
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
f4355ac7a42e   edge-video-analytics-microservice   283.11%   322.6MiB / 31.18GiB   1.01%     42.8kB / 2.69kB   0B / 573kB    36
```

* docker stats with batch-size as 16, no of streams as 1
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
6a3ccbc9fb44   edge-video-analytics-microservice   281.32%   811.7MiB / 31.18GiB   2.54%     42.5kB / 2.83kB   0B / 0B       37
```

* docker stats with batch-size as 1, no of streams as 4
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
f842a3f617c8   edge-video-analytics-microservice   1169.10%   462.7MiB / 31.18GiB   1.45%     46.3kB / 4.18kB   0B / 352kB    55
```

* docker stats with batch-size as 16, no of streams as 4
```sh
CONTAINER ID   NAME                                CPU %     MEM USAGE / LIMIT   MEM %     NET I/O           BLOCK I/O     PIDS
5b1c3b35ddfe   edge-video-analytics-microservice   1170.64%   999.2MiB / 31.18GiB   3.13%     45.4kB / 4.05kB   0B / 123kB    55
```