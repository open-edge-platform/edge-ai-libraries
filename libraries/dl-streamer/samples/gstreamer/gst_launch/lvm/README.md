# Large Vision Model Sample (gst-launch command line)

This sample demonstrates the Large Vision Model (CLIP) pipeline constructed via `gst-launch-1.0` command-line utility. It allows the extraction of image embeddings (CLS tokens) for each frame using the Visual Transformer.


## How It Works
The sample utilizes GStreamer command-line tool `gst-launch-1.0` which can build and run a GStreamer pipeline described in a string format.
The string contains a list of GStreamer elements separated by an exclamation mark `!`, each element may have properties specified in the format `property=value`.

This sample builds a GStreamer pipeline of the following elements:
* `filesrc`, `urisourcebin`, or `v4l2src` for input from file/URL/web-camera
* `decodebin3` for video decoding
* `videoconvert` for converting video frames into different color formats
* `videoscale` for scaling video frames
* `vapostproc` for post-processing (used in GPU pipeline)
* `gvainference` for running inference using the CLIP Vision Transformer model
* `gvametaconvert` for converting metadata to JSON format
* `gvametapublish` for publishing metadata to a file
* `gvafpscounter` for measuring FPS (used in FPS mode)
* `fakesink` for discarding the output

## Model

The sample uses the `clip-vit-large-patch14` model from [Hugging Face](https://huggingface.co/openai/clip-vit-large-patch14). The necessary conversion to the OpenVINO™ format is performed by the `download_public_models.sh` script located in the `samples` directory.

## Running


    ./generate_frame_embeddings.sh [INPUT] [DEVICE] [OUTPUT]


The sample takes three command-line *optional* parameters:
1. [INPUT] to specify the input source.  
The input could be:
    * local video file
    * web camera device (e.g., `/dev/video0`)
    * RTSP camera (URL starting with `rtsp://`) or other streaming source (e.g., URL starting with `http://`)  
If the parameter is not specified, the sample by default streams a video example from an HTTPS link (utilizing the `urisourcebin` element), so it requires an internet connection.

2. [DEVICE] to specify the device for inference.  
   You can choose either `CPU` or `GPU`.
3. [OUTPUT] to choose between file output mode and FPS throughput mode:
    * json - output to a JSON file (default)
    * fps - FPS only

## Sample Output

The sample:
* prints the `gst-launch-1.0` full command line into the console
* starts the command and either publishes metadata to a file or prints out FPS if you set OUTPUT=fps

## See also
* [Samples overview](../../README.md)

## Example Usage

To run the sample with default values:

    ./generate_frame_embeddings.sh

To specify a source file, device, and output:
 
    ./generate_frame_embeddings.sh /path/to/video.mp4 GPU fps

To specify a URL, device, and output:
 
    ./generate_frame_embeddings.sh https://example.com/video.mp4 CPU json

 
To specify a video device, device, and output:

    ./generate_frame_embeddings.sh /dev/video0 CPU fps