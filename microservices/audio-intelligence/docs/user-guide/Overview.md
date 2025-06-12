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

The Model Registry microservice works by serving as a centralized repository for models where, their versions, and metadata are stored. The software behind the microservice is designed to handle the storage, versioning, and metadata management of each model. It also provides functionalities for storing, searching and retrieving model artifacts via a RESTful API.

The software fulfills the promise described in the Overview via its various components.

## High-Level System View Diagram
![Architecture Diagram](images/Model_Registry_HLA.png)  
*Figure 1: High-level system view demonstrating the microservice.*

**Model Registry**

The Model Registry provides REST API endpoints as the primary interface for interacting with the microservice. These endpoints allow users to perform various operations such as registering new models, updating, retrieving and deleting existing models.

**Relational Database**

The Relational Database is responsible for storing structured data related to the models.

**Object Storage**

The Object Storage solution is used to store unstructured data, such as model binaries and other files.

**Intel® Geti™ Software**

The Intel® Geti™ software is accessible via optional configurations within the model registry. Once configured, the model registry is able to access the projects and models hosted within a remote Geti platform. 

## Key Features
* **Feature 1**: Provides a comprehensive set of REST API endpoints for operations such as registering, updating, retrieving, and deleting models.
* **Feature 2**: Utilizes a relational database to store structured data related to models, ensuring data integrity.
* **Feature 3**: Leverages an object storage solution for scalable storage and retrieval of unstructured data, including model binaries and artifacts.
* **Feature 4**: Offers optional configurations to integrate with the Intel® Geti™ software, enabling access to projects and models hosted on a remote Geti platform.

## Supporting Resources

* [Get Started Guide](get-started.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
