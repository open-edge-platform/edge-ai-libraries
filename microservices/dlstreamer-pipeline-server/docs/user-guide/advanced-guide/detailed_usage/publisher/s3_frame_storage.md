# S3 Frame Storage

DL Streamer Pipeline Server supports publishing frames to S3 compatible storage.


**Contents**
  - [Storing Annotated/Unannotated data](#storing-annotated-or-unannotated-data)
  - [S3_write configuration](#s3_write-configuration)

## Storing annotated or unannotated data
Depending upon the pipeline configured, it can store both annotated and unannotated frames. This is determined by whether the pipeline string has a `gvawatermark` element present or not. To learn more about the element, refer to the information contained [here](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/elements/gvawatermark.md).

## S3_write configuration
Following parameters are supported to configure S3 publishing.
  ```sh
    "S3_write": {
        "bucket": "<name-of-bucket-in-s3-storage>",
        "folder_prefix": "<folder-path-where-frame-will-be-stored>",
        "block": false
    }
  ```

  - `bucket` : Mandatory. Name of the bucket where frames will be stored.
  - `folder_prefix` : Optional. Path of the file where frame will be stored inside the bucket. This path is relative to bucket name mentioned.
  - `block` : Optional. It is `false` by default, meaning s3 write will be asynchronous to MQTT publishing. As a result, there might be a scenario where metadata of frame is present but the s3 has still not finished writing the frame to the storage. If specified as `true`, then s3 write and MQTT publishing will be synchronous. In this case, metadata of the frame will be present in MQTT only after s3 has completed writing the frame to the storage.

`Note` The frames will be stored at `<bucket>/<folder_prefix>/<filename>.<extension>`. `<filename>` will be a unique name for each frame given by DL Streamer Pipeline Server. If the `folder_prefix` is not specified or kept blank, then the frame will be stored at `<bucket>/<filename>.<extension>`

`Note` DL Streamer Pipeline Server supports only writing of object data to S3 storage. It does not support creating, maintaining or deletion of buckets. It also does not support reading or deletion of objects from bucket. DL Streamer Pipeline Server assumes that if the user wants to use this feature, then the user already has a S3 storage with buckets configured.

After making changes to config.json, make sure to save it and restart DL Streamer Pipeline Server. Ensure that the changes made to the config.json are reflected in the container by volume mounting it as mentioned [here](../../../how-to-change-dlstreamer-pipeline.md).

- Once you start DL Streamer Pipeline Server with above changes, you should be able to see frames written to S3 storage. Since we are using Minio storage for our demonstration, you can see the frames being written to Minio by logging into Minio console. You can access the console in your browser - http://<S3_STORAGE_HOST>:9090 You can use the credentials specified above in the `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/.env` to login into console. After logging into console, you can go to your desired buckets and check the frames stored.

`Note` Minio console is running at port 9090 by default.

To learn how to publish frames to S3 storage, refer the tutorial [here](../../../how-to-store-s3-frame.md).
