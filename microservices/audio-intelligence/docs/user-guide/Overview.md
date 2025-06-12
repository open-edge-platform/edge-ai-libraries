# Audio Intelligence
Audio Intelligence microservice is used to generate transcription of audio from video files. 

## Overview
The Audio Intelligence microservice provides an automated solution for extracting and transcribing audio from video files. Designed for seamless integration into modern AI pipelines this microservice enables converting spoken content within videos into accurate, searchable text. By leveraging state-of-the-art speech-to-text models, the service supports a wide range of audio formats and languages, making it suitable for diverse applications such as video summary, media analysis, compliance monitoring, and content indexing.

The microservice operates by first isolating the audio track from the input video file. Once extracted, the audio is processed using advanced transcription models to generate a time-aligned text transcript. This transcript can be used for downstream tasks such as keyword search, sentiment analysis, or integration with other AI-driven analytics.

Key features include robust handling of noisy or low-quality audio, support for batch and real-time processing, and easy deployment as a RESTful API. The service is optimized for edge and cloud environments, ensuring low latency and scalability. Developers can interact with the microservice through simple API endpoints, enabling rapid integration into existing workflows.

By automating the extraction and transcription of audio from video, the Audio Intelligence microservice streamlines content analysis, improves accessibility, and unlocks new possibilities for leveraging audio data in various video analytics use cases.

**Key Benefits**
* **Benefit 1**: Enables multimodal analysis of video data by extracting information from its audio track.
* **Benefit 2**: Seamless integration through RESTful APIs with various video analytics use cases that benefit from audio processing.
* **Benefit 3**: Flexibility to use different ASR models as per use case requirements.

**Features**
* **Feature 1**: Extract audio from video files.
* **Feature 2**: Transcribe speech using Whispercpp (CPU).
* **Feature 3**: RESTful API with FastAPI.
* **Feature 4**: Containerization with Docker.
* **Feature 5**: Automatic model download and conversion on startup.
* **Feature 6**: Persistent model storage.
* **Feature 7**: OpenVINO acceleration support for Intel hardware.
* **Feature 8**: **MinIO integration** for video source and transcript storage.

**Use Cases**

Audio Intelligence microservice can be applied to various real-world use cases and scenarios across different video analytics use cases cutting across different industry segments. The motivation to provide the microservice primarily comes from enhancing the accuracy of the video summary pipeline. Here are some examples:
* **Use case 1**: Ego centric videos as captured in industry segments like Safety and Security, Body worn camera for example, benefits from additional modality of information that Audio transcription provides.
* **Use case 2**: Videos from class rooms are primarily analysed using their audio content. Audio intelligence microservice helps provide transcription which can be used to chapterize a class room session, for example.
* **Use case 3**: Courtroom or Legal Proceedings with legal hearings or depositions are primarily analysed using the spoken word.
* **Use case 4**: Video podcasts or interview recordings where the value is in the conversation, discussions, or interviews, and visuals are secondary.
* **Use case 5**: Events, like Panel Discussions and Debates, where multiple speakers discuss or debate topics, the audio contains the key arguments and insights.

# How It Works

The Audio Intelligence microservice accepts a video file for transcription from either file system or minIO storage. Using the configured Whisper model, the transcription is created. The output transcription along with the configured metadata is then stored in configured destination location. It provides a RESTful API to configure and utilize the capabilities.

## Supporting Resources

* [Get Started Guide](get-started.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
