# Video Summarization Architecture Overview

The application is built on a modular microservices approach. 

## Architecture

The following figure shows the system architecture:

![System architecture](./images/TEAI_VideoSumm.drawio.svg)

*Figure 1: Video Summarization system architecture

The following are the Video Summarization pipeline's components:

1. **Video Summarization UI**: You can use the reference UI to interact with and raise queries to the Video Summarization sample application.

2. **Video Summarization pipeline manager**: The pipeline manager is the central orchestrator of the Video Summarization pipeline. It receives the requests from the UI and uses the other set of microservices to deliver the Video Summarization capability.  It can handle videos asynchronously.

3. **Video Ingestion**: The Video Ingestion microservice, which is based on the Deep Learning Streamer (DL Streamer) pipeline, ingests common video formats that require summarization. The ingestion microservice creates video chunks, extracts configured frames from them, passes the frame(s) through object detection, and outputs the metadata and video chunks to the object store.

4. **VLM as the captioning block**: The VLM microservice generates captions for a specific video chunk. The VLM accepts prompts that also include additional information from configured capabilities, such as object detection, and generates a caption. The caption information is stored in the object store.

5. **LLM as the summarizer of captions**: The LLM microservice generates a summary of the individual captions. You can also use the LLM to summarize at the chunk level, where it summarizes captions of individual frames of the chunk.

6. **Audio transcription**: The Audio transcription microservice transcribes the audio channel in the given video. The extracted audio transcription serves as another source of metadata that can be used as an input to VLM, and separately as text data, to enrich the summary.

## Detailed Architecture Overview
<!--
**User Stories Addressed**:
- **US-7: Understanding the Architecture**
  - **As a developer**, I want to understand the architecture and components of the application, so that I can identify customization or integration points.

**Acceptance Criteria**:
1. An architectural diagram with labeled components.
2. Descriptions of each component and their roles.
3. How components interact and support extensibility.
-->

The following figure shows the architecture:

### Architecture Diagram
![Video Summarization technical architecture](./images/TEAI_VideoSumm_Arch.png)

*Video summarization technical architecture

The Video Summarization UI feeds videos to the Video Summarization Pipeline Manager microservice and provides continuous updates throughout the Video Summarization process.

You can configure specific capabilities in the Video Summarization pipeline through the UI, as shown in the architecture. The Video Summarization Pipeline Manager manages your requests.

The VLM, LLM, and Embedding microservices are provided as part of Intel's Edge AI inference microservices catalog, supporting open-source models that can be downloaded from model hubs, for example [Hugging Face Hub models that integrate with OpenVINO™ toolkit](https://huggingface.co/OpenVINO). 

The video ingestion microservice ingests common video formats, chunks the videos, and feeds the extracted frames into configurable capabilities, such as object detection. It then provides the outputs to the VLM microservice for captioning. 

The LLM microservice provides final summaries of videos by summarizing the individual captions. The audio transcription microservice uses the Whisper model to transcribe the audio. The raw videos, frames, and generated metadata are saved in the object store.

### Application Flow

The following are steps in the application flow:

1. **Create the Video Summarization pipeline**

   - **Configure the pipeline**: The Video Summarization UI microservice allows you to configure capabilities on the Video Summarization pipeline. You can see configuration examples for the Video Summarization pipeline [here](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/sample-applications/video-search-and-summarization/cli/config).

   - **Create the pipeline**: The Video Summarization Pipeline Manager configures the pipeline based on your input.  

2. **Input Video Sources**:

   - **Provide the video**: You will provide the video to be summarized. You can also configure the video through the UI. Currently, only offline video processing is supported through reading from local storage. In the future, live camera-streaming will be supported. The pipeline manager stores the video in a local object store.

   - **Ingest the video**: The Video Ingestion microservice consumes the stored video. The microservices reuses the DL Streamer pipeline server and its capabilities to provide features such as object detection, audio classification, and (in future) input feed from live cameras. The ingestion process involves decoding, chunking, and selecting frame(s) from the input video. The extracted frame(s) is passed through object detection blocks, or the audio classification block if they are configured. The extracted frames and the metadata returned by the object detector and/or audio classification are then passed to the VLM microservice.

   - **Transcribe the audio**: The video is demuxed, and its audio extracted for transcription. The audio is fed to the Audio Transcription Microservice through the object store to create a transcription. The transcription is stored in the object store.

3. **Create a caption for given frame(s)**

   - **VLM microservice**: The extracted frame(s) and the prompt and metadata returned from the object detector and/or audio classification are passed to  _vlm-ov-serving_ for captioning. Depending on the configuration and compute availability, batch captioning is also supported. To optimize for performance, captioning is done in parallel with video ingestion.

   - **VLM model selection**: The VLM microservice's capabilities depend on the VLM model used. For example, some models allow multi-frame captioning. The quality of the VLM output depends on the prompt you provide.

   - **Store the captions**: The captions and metadata generated in the pipeline are stored in the local object store. The storage also maintains the necessary relationship information between the stored data.

4. **Create a summary of all captions**:

   - **LLM microservice**: The LLM microservice creates a summary of individual captions. The accuracy of the summary depends on the selected LLM model.

5. **Observability dashboard**: 

   - If set up, the dashboard displays real-time logs, metrics, and traces that provide a view of the application's performance, accuracy, and resource consumption.

The following figure shows the application flow, including the APIs and data sharing protocols:
![Data flow diagram](./images/VideoSummary-request.jpg)

*Figure 3: Data flow for Video Summarization mode

## Key Components and Their Roles
<!--
**Guidelines**:
- Provide a short description for each major component.
- Explain how it contributes to the application and its benefits.
-->

The key components of the Video Summarization mode are as follows:

1. **Intel's Edge AI Inference microservices**:
   - **What it is**: Inference microservices are the VLM, LLM, and audio transcription microservices that run the chosen models on the hardware optimally.
   - **How it is used**: Each microservice uses OpenAI APIs to support its functionality. The microservices are configured to use the required models and are ready. The video pipeline manager accesses these microservices through the APIs.
   - **Benefits**: Intel guarantees that the sample application's default microservices configuration is optimal for the chosen models and the target deployment hardware. Standard OpenAI APIs ensure easy portability of different inference microservices.

2. **Video Ingestion microservice**:
   - **What it is**: This microservice, which reuses the DL Streamer pipeline server, ingests videos, extracts audio, creates chunks, detects objects, classifies audio, and feeds the extracted information and generated metadata to the next stage of processing.
   - **How it is used**: This microservice provides a REST API endpoint that can be used to manage the contents. The Video pipeline manager uses this API to access its capabilities.
   - **Benefits**: DL Streamer pipeline server is a standard offering by Intel, which is optimized for media- and vision analytics-based inference tasks. See the DL Streamer pipeline server documentation for details.

3. **Video Summarization Pipeline manager microservice**:
   - **What it is**: This microservice orchestrates the pipeline per user configuration. The pipeline manager uses a message bus to coordinate across different microservices and also provides performance-motivated capabilities like batching and parallel handling of multiple operations.
   - **How it is used**: The UI front-end uses a REST API endpoint to send user queries and trigger the summarization pipeline.
   - **Benefits**: The microservice provides a reference on how different microservices are orchestrated.

4. **Video Summarization UI microservices**:
   - **What it is**: The UI microservice allows you to interact with the sample application. You can configure the capabilities and input video details, and trigger the Video Summarization pipeline.
   - **How it is used**: To interact with this microservice, you will use the UI interface.
   - **Benefits**: You can treat this microservice as a reference implementation.

5. **Dependent microservices**:
   The pipeline uses dependent microservices to realize the Video Summarization features. The dependent microservices are divided into inference microservices and data-handling microservices:

   **Inference microservices**:

   - [Multimodal Embedding](../../../../microservices/multimodal-embedding-serving/)

   - [Audio Analyzer](../../../../microservices/audio-analyzer/) 

   - [VLM microservice](../../../../microservices/vlm-openvino-serving/) 

    **Data-handling microservices**

   - [VDMS-based data preparation](../../../../microservices/visual-data-preparation-for-retrieval/vdms/)
   
   See the respective documentation for details.

## Extensibility

The Video Summarization mode is modular and allows you to:

1. **Change inference microservices**:

   - The default option is OpenVINO™ model server. You can use other model servers, for example, the Virtual Large Language Model (vLLM) with OpenVINO model server as backend, and the Text Generation Inference (TGI) toolkit to host Embedding and Vision-Language Models (VLMs), but Intel has not validated this method.

   - The compulsory requirement is OpenAI API compliance. Intel does not guarantee that other model servers will provide the same performance as the default options.

2. **Load different VLM and LLM models**:

   - Use models from Hugging Face Hub that integrate with OpenVINO toolkit, or from vLLM model hub. The models are passed as parameters to the corresponding model servers.

3. **Configure different capabilities on the Video Summarization pipeline**: 

   - In addition to available capabilities, you can enable new capabilities if it makes summaries more accurate.

   - You can configure the UI, pipeline manager, and required microservices easily for such extensions.

4. **Deploy on diverse Intel target hardware and deployment scenarios**:

   - Follow the system requirements guidelines on the options available.

## Next Steps
- [Get Started](./get-started.md)
