# Video Search Architecture Overview

The Video Search mode allows developers to customize and deploy the sample application in an on-premises environment and on their private video store without compromising on the accuracy of the responses. The application is built on a modular microservices approach using popular [LangChain\* framework](https://www.langchain.com/). This page provides a technical overview of the application’s architecture, components, and extensibility.

## Purpose

The Video Search pipeline is designed to:
- Demonstrate how you can use Intel® Edge AI catalog of inference microservices to quickly build and deploy on Intel Edge AI systems' portfolio. 
- Serve as a blueprint for building similar scalable and modular solutions that can be deployed on Intel Edge AI systems.
- Showcase how popular frameworks like LangChain framework can be used to quickly implement or customize a video search pipeline and deploy the same on Intel Edge AI systems.
- Showcase the competitiveness of Intel Edge AI systems to address varied deployment scenario requirements (edge-to-cloud).
- Provide reference sample microservices for capabilities like video ingestion and UI frontend that reduces the effort to customize the application.

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

Video Search pipeline is a combination of the core LangChain application logic that implements the Video Search pipeline and the set of microservices that implements the salient blocks of the video search pipeline. The following figures illustrate the setup. The Video Search UI communicates with the Video Search backend microservice. The VLM and embedding microservices are provided as part of Intel Edge AI inference microservices catalog supporting a rich set of open-source models that can be downloaded from popular model hubs. For example, the [Hugging Face OpenVINO toolkit](https://huggingface.co/OpenVINO), a model from Hugging Face\* Model Hub that has been optimized using Intel's OpenVINO™ toolkit. The video ingestion microservice can ingest common video formats, convert it into embedding space, and store it in the vector database. You can also save a copy of the video to the object store.

### Technical Architecture Diagram
![Technical Architecture Diagram of video ingestion](./images/TEAI_VideoSearch_Arch-ingest.png)

*Figure 1: Architecture of video ingestion process

![Technical Architecture Diagram of video query](./images/TEAI_VideoSearch_Arch-query.png)

*Figure 2: Architecture of video query process

### Application Flow
1. **Input Sources**:
   - **Videos**: The video ingestion microservice supports ingesting from common video formats. Currently, the ingestion supports ingesting video only from video files. Support for live streaming input is not provided yet.
   
2. **Create the context**

   - **Upload input videos**: The UI microservice allows the developer to interact with the application through the defined application API. The UI microservice provides the interface to upload the videos on which the search pipeline will be executed. The videos are uploaded and stored in object store. The application stores videos in the MinIO\* database. The ingestion of videos can be done on a continuous basis from pre-configured folder locations. This allows for deployment of the pipeline in live surveillance kind of scenarios.
   
   - **Convert to embeddings space**: The Video ingestion microservice creates the embeddings from the uploaded videos using the embedded microservice. The applicaion stores the embeddings in a vector database. The sample application uses VDMS.
   
3. **Query flow**

   - **Ask a query**: The UI microservice provides a prompt window for user queries.
   
   - **Execute the search pipeline**: The Video Search backend microservice do the following to generate the output response using the search pipeline:
      - Converts the query into an embedding space using the Embeddings microservice.
	  
      - Does a semantic retrieval to fetch the relevant videos from the vector database. Currently, the top-k (with k being configurable) video is used. Does not use a reranker microservice currently.
	  
      - Uses the retrieved videos and associated metadata as part of the prompt to the VLM model, and generates a response using the VLM microservice that hosts the configured VLM model.
	  
4. **Output Generation**:
   - **Response**: Sends the generated response from the VLM microservice to the UI for your display and use.
   
   - **Observability dashboard**: If set up, the dashboard displays real-time logs, metrics, and traces providing a view of the performance, accuracy, and resource consumption by the application.  

The following figure shows the application flow, including the APIs and data sharing protocols:
![Data flow figure](./images/VideoSearch-request.jpg)
*Figure 3: Data flow for Video Search sample application

## Key Components and Their Roles
<!--
**Guidelines**:
- Provide a short description for each major component.
- Explain how it contributes to the application and its benefits.
-->

1. **Intel Edge AI Inference microservices**:
   - **What it is**: Inference microservices are the VLM, embeddings, and reranker microservices that run the chosen models on the hardware, optimally. 
   - **How it is used**: Each microservice uses OpenAI\* APIs to support their functionality. The microservices are configured to use the required models and are ready. The Video Search backend accesses these microservices in the LangChain\* application which creates a chain out of these microservices.
   - **Benefits**: Intel guarantees that the sample application's default microservices configuration is optimal for the chosen models and the target deployment hardware. Standard OpenAI APIs ensure easy portability of different inference microservices.

2. **Video ingestion microservice**:
   - **What it is**: Video ingestion microservice can ingest contents from videos, create the necessary context, and retrieve the right context based on user query.
   - **How it is used**: Video ingestion microservice provides a REST API endpoint that can be used to manage the contents. The Video Search backend uses this API to access its capabilities.
   - **Benefits**: The core part of the video ingestion microservice is the vector handling capability that is optimized for the target deployment hardware. You can select the vector database based on performance considerations. Reference video ingestion is provided in the implementation.

3. **Video Search backend microservice**:
   - **What it is**: Video Search backend microservice is a LangChain framework-based implementation of Video Search's RAG pipeline, which handles user queries.
   - **How it is used**: The UI frontend uses a REST API endpoint to send user queries and trigger the search pipeline.
   - **Benefits**: The microservice provides a reference on using the LangChain framework for implementing Video Search through Intel Edge AI inference microservices.

4. **Video Search UI**:
   - **What it is**: A reference frontend providing an interface for you to interact with the Video Search search pipeline.
   - **How it is used**: The UI microservice runs on the deployed platform on a certain configured port. Accessing the specific URL allows you to use the UI.
   - **Benefits**: This microservice must be treated as a sample reference implementation.

## Extensibility

Intel designed the Video Search sample application with modularity, allowing developers to:

1. **Change inference microservices**:

   - The default option is OpenVINO model server. Use other model servers like Very Large Language Model (VLLM) with OpenVINO model server as backend and Text Generation Inference (TGI) to host Vision-Language Models (VLMs).
   - The mandatory requirement is OpenAI API compliance. Note that Intel does not guarantee that other model servers can provide the same performance compared to the default options.
   
2. **Load different VLM, embedding, and reranker models**:

   - Use different models from Hugging Face OpenVINO Toolkit or vLLM model hub. The models are passed as a parameter to corresponding model servers.
   
3. **Use other generative AI frameworks like Haystack\* framework and LlamaIndex\* tool**:

   - Integrate the inference microservices into an application backend developed on other frameworks similar to the LangChain framework integration provided in this sample application.
   
4. **Deploy on diverse target Intel® hardware and deployment scenarios**:

   - Follow the system requirements guidelines on the different options available.

## Next Steps
- [Get Started](./get-started.md)