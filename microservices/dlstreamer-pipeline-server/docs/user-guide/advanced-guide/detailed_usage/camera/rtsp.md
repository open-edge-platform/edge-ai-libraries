# RTSP Cameras

- Refer the following pipeline for RTSP camera and modify the appropriate config.json file in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs` directory.

```sh
  "pipeline": "rtspsrc location=\"rtsp://<USERNAME>:<PASSWORD>@<RTSP_CAMERA_IP>:<PORT>/<FEED>\" latency=100 name=source ! rtph264depay ! h264parse ! decodebin ! videoconvert ! video/x-raw,format=RGB ! appsink name=destination"
```

> **Note:** The RTSP URI of the physical camera depends on how it is configured using the camera software. You can use VLC Network Stream to verify the RTSP URI to confirm the RTSP source. 

> **Note:**  If you are deploying DL Streamer Pipeline Server behind proxy environment, make sure that <RTSP_CAMERA_IP> address is specified under `no_proxy` environment variable.

> **Note:** For more information on the RTSP URI please refer the website/tool of the camera software which is used to configure the RTSP camera. For information on RTSP protocol refer <https://en.wikipedia.org/wiki/Real_Time_Streaming_Protocol>



**Simulating RTSP streaming Cameras**

- Start RTSP using open source RTSPATT docker image
  - Run the following command to create a RTSP stream:

    ```sh
    docker run --rm -e RTSP_RESOLUTION='1920'x'1080' -e RTSP_FRAMERATE=25 -p 8554:8554 ullaakut/rtspatt:latest
    ```

  If more options are required to generate a RTSP stream refer
  the following link:
  <https://hub.docker.com/r/ullaakut/rtspatt/>


- Start cvlc based RTSP stream
  - Install VLC if not installed already: `sudo apt install vlc`
  - In order to use the RTSP stream from cvlc, the RTSP server must be started using VLC with the following command:

        `cvlc -vvv file://<absolute_path_to_video_file> --sout '#gather:rtp{sdp=rtsp://<SOURCE_IP>:<PORT>/<FEED>}' --loop --sout-keep`

      **Note:** `<FEED>` in the cvlc command can be `live.sdp` or it can also be avoided. But make sure the same RTSP URI given here is
      used in the ingestor pipeline config.
