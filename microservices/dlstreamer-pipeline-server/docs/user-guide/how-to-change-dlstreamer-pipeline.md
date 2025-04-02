# How to change DLStreamer pipeline

## Steps

EVAM supports dynamic update of pipeline parameters using REST API. Users are required to provide required placeholders in `[EVAM_WORKDIR]/configs/default/config.json` to make it configurable at run-time of EVAM container. Follow instruction in the [Prerequisite section](./how-to-update-default-config.md#prerequisite-for-tutorials) to create a sample configuration file.

In case users want to update default pipeline, they need to update the same in configuration file that EVAM loads. Users can mount updated config files from host systems on to EVAM containers by updating `[EVAM_WORKDIR]/docker/docker-compose.yml`. To get you started, instruction to create sample docker compose file is available [here](./get-started.md#pull-the-image-and-start-container). Refer below snippets:

```sh
    volumes:
      # Volume mount [WORDDIR]/configs/default/config.json to config file that EVAM container loads."
      - "../configs/default/config.json:/home/pipeline-server/config.json"
```
As an example we are creating `video-ingestion and resize` pipeline. We need to update `pipeline` key in `[EVAM_WORKDIR]/configs/default/config.json` as shown below.  It would create DLStreamer pipeline that reads user provided video file, decodes it, and resize to 1280x720.
Note: Follow instruction in the [Prerequisite section](./how-to-update-default-config.md#prerequisite-for-tutorials) to create a sample configuration file.
```sh
"pipeline": "{auto_source} name=source  ! decodebin ! videoscale ! video/x-raw, width=1280,height=720 ! gvametapublish name=destination ! appsink name=appsink",
```
`Note`: If needed users can change pipeline name by updating `name` key in `config.json`. If user is updating this field, accordingly endpoint in curl request needs to be changed to `<SERVER-IP>:<PORT>/pipelines/user_defined_pipelines/<NEW-NAME>`. In this example, we are only changing pipeline.

Once update, user needs to restart EVAM containers to reflect this change. Run these commands from `[EVAM_WORKDIR]/docker/` folder.
Note: To get you started, instruction to create sample docker compose file is available [here](./get-started.md#pull-the-image-and-start-container)

```sh
docker compose down

docker compose up
```

Above steps will restart EVAM and load `video-ingestion and resize` pipeline. Now to start this pipeline, run below Curl request. It would start DLStreamer pipeline that reads `classroom.avi` video file with resolution of 1920x1080 and after resizing to 1280x720, it would stream over RTSP. Users can view this on any media player e.g. vlc, ffplay etc.

RTSP Stream will be accessible at `rtsp://<SYSTEM_IP_ADDRESS>:8554/classroom-video-streaming`.

```sh
curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
                "source": {
                    "uri": "file:///home/pipeline-server/resources/videos/classroom.avi",
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
                        "path": "classroom-video-streaming"
                    }
                }
}'
```
