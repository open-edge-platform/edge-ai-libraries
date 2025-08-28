Audio Analyzer
==============

Audio Analyzer microservice is used to generate transcription of audio from video files.

Overview
########

The Audio Analyzer microservice provides an automated solution for extracting and transcribing audio from video files. Designed for seamless integration into modern AI pipelines this microservice enables converting spoken content within videos into accurate, searchable text. By leveraging state-of-the-art speech-to-text models, the service supports a wide range of audio formats and languages, making it suitable for diverse applications such as video summary, media analysis, compliance monitoring, and content indexing.

The microservice operates by first isolating the audio track from the input video file. Once extracted, the audio is processed using advanced transcription models to generate a time-aligned text transcript. This transcript can be used for downstream tasks such as keyword search, sentiment analysis, or integration with other AI-driven analytics.

Key features include robust handling of noisy or low-quality audio, support for batch and real-time processing, and easy deployment as a RESTful API. The service is optimized for edge and cloud environments, ensuring low latency and scalability. Developers can interact with the microservice through simple API endpoints, enabling rapid integration into existing workflows.

By automating the extraction and transcription of audio from video, the Audio Analyzer microservice streamlines content analysis, improves accessibility, and unlocks new possibilities for leveraging audio data in various video analytics use cases.

**Key Benefits**
- **Benefit 1**: Enables multimodal analysis of video data by extracting information from its audio track.
- **Benefit 2**: Seamless integration through RESTful APIs with various video analytics use cases that benefit from audio processing.
- **Benefit 3**: Flexibility to use different ASR models as per use case requirements.

**Features**
- **Feature 1**: Extract audio from video files.
- **Feature 2**: Transcribe speech using Whispercpp (CPU).
- **Feature 3**: RESTful API with FastAPI.
- **Feature 4**: Containerization with Docker.
- **Feature 5**: Automatic model download and conversion on startup.
- **Feature 6**: Persistent model storage.
- **Feature 7**: OpenVINO acceleration support for Intel hardware.
- **Feature 8**: **MinIO integration** for video source and transcript storage.

**Use Cases**

Audio Analyzer microservice can be applied to various real-world use cases and scenarios across different video analytics use cases cutting across different industry segments. The motivation to provide the microservice primarily comes from enhancing the accuracy of the video summary pipeline. Here are some examples:

- **Use case 1**: Ego centric videos as captured in industry segments like Safety and Security, Body worn camera for example, benefits from additional modality of information that Audio transcription provides.
- **Use case 2**: Videos from class rooms are primarily analysed using their audio content. Audio Analyzer microservice helps provide transcription which can be used to chapterize a class room session, for example.
- **Use case 3**: Courtroom or Legal Proceedings with legal hearings or depositions are primarily analysed using the spoken word.
- **Use case 4**: Video podcasts or interview recordings where the value is in the conversation, discussions, or interviews, and visuals are secondary.
- **Use case 5**: Events, like Panel Discussions and Debates, where multiple speakers discuss or debate topics, the audio contains the key arguments and insights.

How It Works
############

The Audio Analyzer microservice accepts a video file for transcription from either file system or minIO storage. Using the configured Whisper model, the transcription is created. The output transcription along with the configured metadata is then stored in configured destination location. It provides a RESTful API to configure and utilize the capabilities.

Models supported
################

The service automatically downloads and manages the required models based on configuration. Two types of models are supported:

1. **GGML Models** Primarily used for inference on CPU using whispercpp backend.
2. **OpenVINO Models** Optimized for GPU inference on Intel GPUs.

Models are downloaded on application startup, converted to OpenVINO format if needed, and stored in persistent volumes for reuse. The conversion process includes:
- Downloading the original Hugging Face Whisper model
- Converting the PyTorch model to OpenVINO format.
- Storing the encoder and decoder components separately for efficient inference

Available Whisper Models
++++++++++++++++++++++++

The following Whisper model variants are supported by the service (for both GGML and OpenVINO formats):

 =========== ================== ======== ==============
  Model ID    Description        Size     Languages
 =========== ================== ======== ==============
  tiny        Tiny model         ~75M     Multilingual
  tiny.en     Tiny model         ~75M     English-only
  base        Base model         ~150M    Multilingual
  base.en     Base model         ~150M    English-only
  small       Small model        ~450M    Multilingual
  small.en    Small model        ~450M    English-only
  medium      Medium model       ~1.5GB   Multilingual
  medium.en   Medium model       ~1.5GB   English-only
  large-v1    Large model (v1)   ~2.9GB   Multilingual
  large-v2    Large model (v2)   ~2.9GB   Multilingual
  large-v3    Large model (v3)   ~2.9GB   Multilingual
 =========== ================== ======== ==============


Supporting Resources
####################

- :doc:`Get Started Guide <./get-started>`
- :doc:`API Reference <./api-reference>`
- :doc:`System Requirements <./system-requirements>`

.. toctree::
   :hidden:
   :maxdepth: 2

   overview-architecture
   system-requirements
   get-started
   how-to-build-from-source
   api-reference
   release-notes
