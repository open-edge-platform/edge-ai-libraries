Run object detection on a video file using DL Streamer Pipeline Server:
- Start the pipeline server service using Docker Compose
- Launch the pallet_defect_detection pipeline on the warehouse.avi video file
- Use CPU for inference
- Output the annotated video stream via RTSP at path "det"
- Check the pipeline status to confirm it is running
- View the RTSP output stream at rtsp://localhost:8554/det
- Stop the pipeline when processing is complete
