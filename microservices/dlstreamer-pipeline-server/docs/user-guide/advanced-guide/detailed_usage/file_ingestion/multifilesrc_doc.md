# Multifilesrc Usage

**Contents**

- [Video File with gstreamer ingestor (multifilesrc)](#video-file-with-gstreamer-ingestor-multifilesrc)

## Video File with gstreamer ingestor (multifilesrc)

**NOTE**:

- The videos should follow a naming convention and should be named in the format characters followed by digits in the sequential order. For e.g. `video_001`, `video_002`, `video_003` and so on.
  - Make use of the `%d` format specifier to specify the total digits present in the filename. For example, if the videos are named in the format `video_0001`, `video_0002`, then it has total 4 digits in the filename. Use `%04d` while providing the name `<video_filename>_%04d.mp4`.
  - The ingestion will stop if it does not find the required file name.
  For example, if directory contains videos `video_01`, `video_02` and `video_04`, then the ingestion will stop after reading `video_02` since `video_03` is not present in the directory.
  
- In case one does not want to loop the video with multifilesrc element then set the `loop` property to `FALSE`

- In case one wants to play a single video for specific number of iterations set the `loop` property to `FALSE` and `stop-index` property to the number of iterations. For example, setting `stop-index=0` would play it once, setting `start-index=1` and `stop-index=5` would play it five times. Setting the `loop` property to `TRUE` will override the `stop-index` property.

- When playing multiple videos from a folder, set the `loop` property to `FALSE` and `start-index` and `stop-index` properties can be set for specifying the range of videos to play in a sequence. For example, if the location is set to `/home/pipeline-server/video_dir/video%03d.avi` and the available videos in the directory are `video001.avi`, `video002.avi`, `video003.avi`, `video004.avi` specifying `start-index=1` and `stop-index=2` will play `video001.avi` and `video002.avi`.
- The `loop` property of `multifilesrc` plugin does not support video files of MP4 format. Hence MP4 video files will not loop and the recommendation is to transcode the video file to AVI format.

- It is recommended to set the `loop` property of the `multifilesrc` element to false `loop=FALSE` to avoid memory bloat issues. If you want to loop the video, please refer [cvlc based RTSP stream](../camera/rtsp.md) option.

- In case one notices general stream error with multifilesrc element when certain video files are used then transcode the video file to `H264` video with `.avi` container format to ensure the compatibility of the format of the video file.