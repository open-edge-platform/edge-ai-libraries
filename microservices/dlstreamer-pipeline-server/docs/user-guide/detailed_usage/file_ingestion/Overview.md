# File Ingestion

* [File based Ingestion](#file-based-ingestion)
    - [Video Ingestion](#video-ingestion)
    - [Image Ingestion](#image-ingestion)

## File based Ingestion

To dynamically specify file as source via REST Request, refer to this [section](../rest_api/customizing_pipeline_requests.md#file-source).

### Video Ingestion
Video ingestion supports reading video files from a directory. Refer to the [doc](./video-ingestion.md) for more details on the usage.

### Image Ingestion
The Image ingestion feature is responsible for ingesting the images coming from a directory for further processing. Refer to the [doc](./image-ingestion.md) for more details on supported image formats and usage.

```{toctree}
:maxdepth: 5
:hidden:
image_ingestion.md
video_ingestion.md
multifilesrc_doc.md
```