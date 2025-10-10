# gvaaudiotranscribe

Performs audio transcription using OpenVino GenAI Whisper model. for more details on the whisper ASR check out [OpenVino GenAI Documentation](https://docs.openvino.ai/2025/api/genai_api/_autosummary/openvino_genai.WhisperPipeline.html#openvino_genai.WhisperPipeline)

This guide serves as a reference for extending custom ASR models.[CUSTOM_HANDLERS.md](/home/intel/workspace/forked/edge-ai-libraries/libraries/dl-streamer/src/monolithic/gst/audio_inference_elements/gvaaudiotranscribe/CUSTOM_HANDLERS.md)

```sh
Element Flags:

Pad Templates:
  SINK template: 'sink'
    Availability: Always
    Capabilities:
      audio/x-raw
                 format: S16LE
                   rate: 16000
               channels: 1

  SRC template: 'src'
    Availability: Always
    Capabilities:
      audio/x-raw
                 format: S16LE
                   rate: 16000
               channels: 1

Element has no clocking capabilities.
Element has no URI handling capabilities.

Pads:
  SINK: 'sink'
    Pad Template: 'sink'
  SRC: 'src'
    Pad Template: 'src'

Element Properties:

  device              : Device to use for inference (CPU, GPU)
                        flags: readable, writable
                        String. Default: "CPU"

  language            : Language code (e.g., <|en|>)
                        flags: readable, writable
                        String. Default: "<|en|>"

  model               : Path to the Whisper model directory (or custom model path for extensible handlers)
                        flags: readable, writable
                        String. Default: null

  model-type          : Model type for inference: 'whisper' (supported), custom types can be implemented
                        flags: readable, writable
                        String. Default: "whisper"

  name                : The name of the object
                        flags: readable, writable
                        String. Default: "gvaaudiotranscribe0"

  parent              : The parent of the object
                        flags: readable, writable
                        Object of type "GstObject"

  qos                 : Handle Quality-of-Service events
                        flags: readable, writable
                        Boolean. Default: false

  return-timestamps   : Whether to return timestamps with transcription
                        flags: readable, writable
                        Boolean. Default: false

  task                : Task: 'transcribe' or 'translate'
                        flags: readable, writable
                        String. Default: "transcribe"

```