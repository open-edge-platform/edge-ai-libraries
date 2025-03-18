# S3 Frame Storage

**Contents**
  - [Enable S3 storage for frames](#enable-s3-storage-for-frames)
    - [S3_write configuration](#s3_write-configuration)


## Enable S3 storage for frames
EVAM supports storing frames from media source into S3 storage. EVAM supports industry standard S3 APIs. Hence, it will be compatible with any S3 storage of your choice. In this example, we will be using Minio database for demonstration. You can enable Minio S3 storage by making following changes to docker compose file present at `[EVAM_WORKDIR]/docker/docker-compose.yml`

- Bring up your minio server by adding `minio` service under `services` section

```sh
minio:
    image: minio/minio:latest  
    hostname: minio-server
    container_name: minio-server
    ports:
      - "9000:9000"  # S3 API
      - "9090:9090"  # MinIO Console UI
    environment:
      MINIO_ROOT_USER: ${S3_STORAGE_USER}  
      MINIO_ROOT_PASSWORD: ${S3_STORAGE_PASS}
    networks:
      - app_network
    command: server --console-address ":9090" /data
```

- Connect to your minio server by adding correct values to following parameters present in `[EVAM_WORKDIR]/docker/.env` file. Make sure that the values match with corresponding values given in the above step -
```sh
S3_STORAGE_HOST=minio-server
S3_STORAGE_PORT=9000
S3_STORAGE_USER=<DATABASE USERNAME> #example S3_STORAGE_USER=minioadmin
S3_STORAGE_PASS=<DATABASE PASSWORD> #example S3_STORAGE_PASS=minioadmin
```

- Add `minio-server` container name to `no_proxy` parameter present under `environment` section of `edge-video-analytics-microservice` service
```sh
no_proxy=$no_proxy,multimodal-data-visualization-streaming,${RTSP_CAMERA_IP},minio-server
```
`Note` The value added (`minio-server`) to `no_proxy` must match with the value of `container_name` specified in the `minio` service section at docker compose file (`[EVAM_WORKDIR]/docker/docker-compose.yml`).

- After updating the above files, replace the default config present at `[EVAM_WORKDIR]/configs/default/config.json` with `[EVAM_WORKDIR]/configs/sample_s3write/config.json`. Make sure you have given correct values for `mqtt_publisher` section and `S3_write` section as per your requirements in config.json. To know more about mqtt publishing you can refer following [section](../publisher/eis_mqtt_publish_doc.md). Explanation for each parameter in `S3_write` section is given below. 

### S3_write configuration
  ```sh
    "S3_write": {
        "bucket": "<name-of-bucket-in-s3-storage>", 
        "folder_prefix": "<folder-path-where-frame-will-be-stored>",
        "block": false
    }
  ```

  - `bucket` : Name of the bucket where frames will be stored. This parameter is a MUST and needs to be specified.
  - `folder_prefix` : Path of the file where frame will be stored inside the bucket. This path is relative to bucket name mentioned. This can be blank as well.
  - `block` : It is `false` by default, meaning s3 write will be asynchronous to MQTT publishing. As a result, there might be a scenario where metadata of frame is present but the s3 has still not finished writing the frame to the storage. If specified as `true`, then s3 write and MQTT publishing will be synchronous. In this case, metadata of the frame will be present in MQTT only after s3 has completed writing the frame to the storage.

`Note` The frames will be stored at `<bucket>/<folder_prefix>/<filename>.<extension>`. `<filename>` will be a unique name for each frame given by EVAM. If the `folder_prefix` is not specified or kept blank, then the frame will be stored at `<bucket>/<filename>.<extension>`

`Note` EVAM supports only writing of object data to S3 storage. It does not support creating, maintaining or deletion of buckets. It also does not support reading or deletion of objects from bucket. EVAM assumes that if the user wants to use this feature, then the user already has a S3 storage with buckets configured.

After making changes to config.json, make sure to save it and restart EVAM. Ensure that the changes made to the config.json are reflected in the container by volume mounting it as mentioned [here](../../Tutorials-Basic.md#change-dlstreamer-pipeline).

- Once you start EVAM with above changes, you should be able to see frames written to S3 storage. Since we are using Minio storage for our demonstration, you can see the frames being written to Minio by logging into Minio console. You can access the console in your browser - http://<S3_STORAGE_HOST>:9090 You can use the credentials specified above in the `[EVAM_WORKDIR]/docker/.env` to login into console. After logging into console, you can go to your desired buckets and check the frames stored.

`Note` Minio console is running at port 9090 by default.