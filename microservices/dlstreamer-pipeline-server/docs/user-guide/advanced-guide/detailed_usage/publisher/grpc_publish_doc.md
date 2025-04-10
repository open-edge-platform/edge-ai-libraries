 # gRPC Publishing post pipeline execution

 **Contents**

- [Overview](#overview)
- [Prerequisites](#prerequisites)
  - [Configuration](#configuration)
- [Secure & Unsecure Publishing](#secure--unsecure-publishing)
- [Multi-pipeline Topic Association](#multi-pipeline-topic-association)
- [Error handling](#error-handling)
- [Known issues](#known-issues)

## Overview

EVAM supports publishing metadata and frame blob using gRPC communication. The messages are published post pipeline execution to one or more grpc clients configured in `config.json`. Depending on the mode of deployment, EIS or standalone, the communication can be secure or unsecure. 

## Prerequisites
One or more gRPC clients must be configured in EVAM's client list in the interfaces section of `config.json`. See below.

### Configuration
```sh
{
    "config": {
    ...

    },
    "interfaces": {
        "Clients": [
            {
                "EndPoint": "multimodal-data-visualization-streaming:65138",
                "Name": "visualizer",
                "Topics": [
                    "edge_video_analytics_results"
                ],
                "Type": "grpc",
                "overlay_annotation": "true"
            }
        ]
    }
}
```

## Secure & Unsecure Publishing
Depending on the mode of deployment (determined by env flag `RUN_MODE=EII/EVA`), the communication can be secure or unsecure. In standalone deployment(`RUN_MODE=EVA`), the communication is unsecure. In EIS deployment(`RUN_MODE=EII`) however, gRPC communication is secure where generation of certificates is taken care of by Config Manager Agent(CMA), another EIS microservice for provisioning.


## Multi-pipeline Topic Association
Metadata in published grpc messages contain `topic` key to uniquely identify the pipeline to which these messages belong. For a configuration with single pipeline only, the client `Topics` are enough to identify the pipeline. But in case of multiple pipelines, to distinguish between messages from which pipeline they belong, we can enable appending pipeline name to the topic value already configured in the respective client interface. To enable this, env var `APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC` must be set to `"true"` in the docker compose file. 

For example, consider a scenario where there are 2 pipelines with names pipelineA and pipelineB  configured in config.json. Also, two clients are configured with topics names configured as topicX and topicY. If the env flag - `APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC` is set, the published topics would be `topicX_pipelineA` and `topicY_pipelineA` for pipelineA and `topicX_pipelineB` and `topicY_pipelineB` for pipelineB. See below.

|           	| topicX               	| topicY               	|
|-----------	|----------------------	|----------------------	|
| pipelineA 	| **topicX_pipelineA** 	| **topicY_pipelineA** 	|
| pipelineB 	| **topicX_pipelineB** 	| **topicY_pipelineB** 	|


## Error handling

- **InactiveRpcError, StatusCode.DEADLINE_EXCEEDED**
    
    Sample error
    ```sh
    2024-10-25 15:25:20,685 : ERROR : root : [edge_grpc_client.py] :send : in line : [109] : <_InactiveRpcError of RPC that terminated with:
            status = StatusCode.DEADLINE_EXCEEDED
            details = "Deadline Exceeded"
            debug_error_string = "UNKNOWN:Error received from peer  {created_time:"2024-10-25T15:25:20.684936173+00:00", grpc_status:4, grpc_message:"Deadline Exceeded"}"
    >
    ```

    **Resolution**: Most likely, the server cannot be reached. 
    
    Please check if the corresponding client services are up/accessible.     
    - Check if endpoints and ports are correct for both server and client(in EVAM client list).
    - Also check if the container name is added to EVAM's `no_proxy` environment variable in docker compose file.

## Known issues
Pipelines where encoding is done by supported publisher such as EVAM's gRPC publisher, CPU consumption spikes have been observed. Especially for CPUs with readily available CPU cores for fast inferencing and encoding, e.g. i9-13000.

Encoding is necessary if we wish to let the publisher do the annotation overlay. If one does not need the overlay, they can let the pipeline do the encoding which is usually better at resource consumption. In this case however, any annotation overlay required now has to be done by a supporting pipeline element such as udfloader. See udfloader flag, `"visualize": "true",`
