# Video Summarization Sample Application [In Progress]

Video summarization sample application using Generative AI Vision Language Models (VLMs) leverages advanced AI techniques to create concise and informative summaries of long-form videos. This technology combines visual, audio, and textual data to understand and extract the most relevant content from videos, enabling efficient content review and improved searchability. 

Video summarization sample application provides a rich pipeline with host of capabilities aiding qualitatively rich response. The application demonstrates that a rich experience can be built using a cost efficient portfolio of Intel AI systems and using Intel's Edge AI microservices catalog. This sample application simplifies the development, customization, and deployment of Video summarization applications in diverse deployment scenarios with out-of-the-box support for on-prem and edge environments.

![Video Summarization web interface](./images/VideoSumm_Webpage.png)

## Table of Contents
1. [Overview and Architecture](#overview-and-architecture)
2. [How to Use the Application](#how-to-use-the-application)

## Overview and Architecture

### Key Features

Leveraging GenAI VLMs, LLMs, object detection, and a host of other configurable capabilities, video summarization application can provide users with a powerful tool to quickly grasp the main points of long-form videos, enhancing productivity and user experience. Key capabilities that a video summarization pipeline should provide includes:

- **Efficient Summarization**: Automatically generate detailed summaries of lengthy videos, highlighting key moments and essential information.
- **Enhanced Searchability**: Improve the ability to search within videos by providing summarized content that can be indexed and queried.
- **Contextual Understanding**: Utilize VLMs to combine audio and visual elements, ensuring a richer and more accurate understanding of the video content.
- **Content Review**: Facilitate quicker and more efficient content review processes by providing concise summaries that capture the essence of the video.
- **Customizable Summarization**: Allow customization of summarization capabilities and parameters to suit specific use cases and preferences, such as focusing on particular topics or themes within the video or enable context extraction from audio etc. The capabilities on the pipeline should be configurable to suit the target application.
- **Scalability**: Handle large volumes of video data, making it suitable for various applications, including media analysis, content management, and personalized recommendations.

The Video summarization sample application provides the above listed capabilities through following features:

- **Rich Video summarization pipeline**: The application provides a host of capabilities that can be used to qualitatively influence the summarization of the given user video. The capabilities help with richer contextual and perceptual understanding of the video. Example: Using an object detector to enrich the quality of prompt given as input to VLM captioning. Further details of configurability is provided in the [architecture overview](./overview-architecture.md) document.
- **Optimized pipeline on Intel Edge AI Systems hardware**: The application is [optimized](./benchmarks.md) to run efficiently on Intel® Edge AI systems, ensuring high performance and reliability.
- **Customizable pipeline with optimized microservices**: The application allows for customization of various components of the pipeline, such as video ingestion, model selection, selection of capabilities enabled on the pipeline, and deployment options to suit specific use cases and deployment scenarios. Intel's Edge AI inference microservices allow developers to customize and adapt specific parts of the application to suit their deployment and usage needs. For example, developers can customize the VLM model with different levels of guardrail capabilities based on segment specific needs. Intel's inference microservices provide the flexibility to tailor the application for specific deployment scenarios and usage requirements without compromising performance on the given deployment hardware.
- **Flexible deployment options**: The application provides options for deployment using Docker Compose and Helm charts, enabling developers to choose the best deployment environment for their needs.
- **Support for a wide range of open-source models**: Intel's Edge AI inference microservices provide flexibility to use the right GenAI models (VLM, Embeddings for example) as required for target usage. The application supports various [open-source models](https://huggingface.co/OpenVINO), allowing developers to select the best models for their use cases.
- **Optimized for Performance**: The default configuration of the pipeline is optimized to run efficiently on target hardware, providing high performance and low cost of ownership.
- **Self-hosting inference**: Perform inference locally or on-premises, ensuring data privacy and reducing latency.
- **Observability and monitoring**: The application provides observability and monitoring capabilities using [OpenTelemetry](https://opentelemetry.io/) & [OpenLIT](https://github.com/openlit/openlit), enabling developers to monitor the application's performance and health in real-time.
- **User-Friendly Interface**: A reference intuitive and easy-to-use interface is provided for users to interact with the Video summarization application.
- **Future extensions**: A sample set of "in-the-works" capabilities are listed below. These are designed as modular capabilities which can be used (or not) specific to deployment requirements.
    - **Natural Language Querying**: The captions generated by the application enables users to search or query video content using natural language queries, making the search process intuitive and user-friendly. This capability allows to combine the video summarization pipeline with Video search pipeline.
    - **Audio capability**: For certain videos, the audio provides richer context which can positively influence the accuracy of the summarization. The audio pipeline will provide a mechanism to create transcription of the audio channel and use the same as additional context information for the VLM.
    - **Verifier as a guardrail**: The verifier block allows to check the output of the VLM for hallucinations. This block uses additional VLM capabilties to cross check the output of the VLM from previous stage. 

### Technical Architecture
The Video summarization sample application and the constituent components are shown in the system architecture diagram. A high-level overview of the components is provided below.

1. **Video summarization UI**: A reference UI is provided for the users to interact with and exercise all capabilities of the video summarization application. 

2. **Video summarization pipeline manager**: The pipeline manager is the central orchestrator of the summarization pipeline. It receives the requests from the UI and uses the other set of microservices to deliver the summarization capability. It provides for asynchronous handling of the video.

3. **Video Ingestion**: This microservice is responsible for ingesting videos that need to be summarized. The ingestion microservice is based on Intel DLStreamer pipeline and utilises the DLStreamer pipeline server (formerly called EVAM) to manage the video pipeline. The video ingestion microservice allows ingestion of common video formats. The ingestion microservice creates video chunks, extracts configured frames from it, passes the frame(s) through object detection and outputs all of the metadata and the video chunks to the object store.  

4. **VLM as the captioning block**: The vlm-openvino-serving is responsible for generating captions for the specific video chunk. The VLM accepts prompts which also includes additional information from configured capabilities (like object detection) and generates the caption. The caption information is stored to the object store.

5. **LLM as the summarizer of captions**: The LLM microservice is used to generate the summary of the individual captions. It is also possible to use the LLM to summarize at a chunk level (captions of individual frames of the chunk) but it is optional.

6. **Audio transcription**: The Audio transcription microservice helps create a transcription of the audio channel in the given video. The extracted audio transcription serves as another source of rich metadata that can be used both as an input to VLM and separately as text data to enrich the summary.

![System Architecture Diagram](./images/TEAI_VideoSumm.png)

Further details on the system architecture and customizable options are available [here](./overview-architecture.md).

## How to Use the Application
Video summarization pipeline provides several capabilities to help address the accuracy requirements of complex long form videos. Deciding which of the capabilities need to be used comes with tradeoff of accuracy versus performance. Hence, the usage of the application starts with answering the following questions:
1. What is the complexity of the video that need to be summarized?
2. What is the accuracy target the summarization pipeline needs to achieve as measured by key qualitative metrics like BERT score as well as from manual inspection?
3. What is the available compute resources to run the pipeline? 
4. What are the key performance metrics like throughput, latency etc. that need to be achieved by the pipeline?

The answer to required  tradeoff follows from the answer to above questions. Subject to the compute and accuracy tradeoff decisions, the configuration and customization of the pipeline is done. The sample application provides several knobs to help achieve the desired tradeoff. Once the pipeline is tuned and desired accuracy hit on the given hardware, the application is ready for deployment. The user is expected to upload the video that needs to be summarized, configure the mandatory parameters like chunk duration, number of frames, overlap, etc. and submit the summarization request. The application provides a continuous update on the progress of the summarization task and prints the final summary at the end of the process. The API spec provides details on the API to be used to access the capability of the application.


Further details on the system architecture and customizable options are available [here](./overview-architecture.md).

Detailed hardware and software requirements are available [here](./system-requirements.md).

To get started with the application, please refer to the [Get Started](./get-started.md) page.