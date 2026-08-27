# VSS sample assets

Verified on this checkout:

- `APP_ROOT/data/` exists but contains no video files. It is the default search watcher directory (`VS_WATCHER_DIR=$PWD/data`) in `setup.sh`, not a populated sample-video folder in this tree.
- Repository video assets found outside `data/`:
  - `APP_ROOT/cli/resources/ceramic_store.mp4`
  - `APP_ROOT/video-ingestion/resources/videos/store-aisle-detection.mp4`

The smoke scripts choose videos in this order:

1. first positional argument, for example `./scripts/e2e_summary.sh /path/to/video.mp4`
2. `VIDEO_PATH` environment variable
3. first video under `APP_ROOT/data/`, if one is later added
4. `APP_ROOT/cli/resources/ceramic_store.mp4`
5. `APP_ROOT/video-ingestion/resources/videos/store-aisle-detection.mp4`

Use a streamable MP4 when supplying your own file. The Pipeline Manager upload controller rejects non-streamable MP4s with `The video file is not streamable. Please upload a streamable MP4 video.`
