# Video Search and Summarization Overview

The Video Search and Summarization mode summarizes long-form videos and searches the generated summary. The mode combines the generative AI Vision Language Models (VLMs) and multimodal embedding models to understand and extract requested content from videos. 

You can develop, customize, and deploy Video Summarization solutions in diverse deployment scenarios with out-of-the-box support for on-premise and edge environments.

The following is the Video Search and Summarization mode UI:

![Video Summary web interface](./images/VideoSearch_Summary_Webpage.png)

## Purpose

The combined Video Search and Summarization mode is useful for rapid access to relevant video content and complex use cases. The following are several examples:

- Security and surveillance teams benefit from semantic search capabilities to identify incidents, suspicious activities, or patterns across hours of footage efficiently, improving response times and situational awareness.

- In education and training, instructors and learners can retrieve key moments or topics from recorded lectures and tutorials, enhancing knowledge discovery and personalized learning.

- Legal and compliance professionals can use search to pinpoint evidence or verify claims within video records, supporting investigations and audits.

- In media and entertainment, editors and analysts can quickly locate and review specific scenes or events within large archives, streamlining content production and compliance checks.

- Marketing, Customer Support, and Product Documentation teams can organize, index, and retrieve valuable content, driving productivity and informed decision-making.

To create a summary with the best possible accuracy for a given compute, the Video Search and Summarization mode:

- Allows you to build the Video Search and Summarization pipeline quickly through Intel’s Edge AI catalog of inference microservices. The inference microservices are optimized for Intel’s Edge AI systems.
	
- Serves as a blueprint for building similar scalable and modular solutions that can be deployed on Intel’s Edge AI systems.
	
- Showcases the competitiveness of Intel’s Edge AI systems to address varied deployment scenarios, from the edge to the cloud.
	
- Provides reference sample microservices for capabilities like video ingestion, embedding generation, vector search, and UI frontend, which reduces the effort to customize the application.

The combined mode shows that the Intel's Edge AI systems portfolio can run complex use cases. The sample application runs in its fullest configuration in the combined mode, thereby showcasing a resource intensive usage. You can customize the application on multiple levels including model configuration, and use it to size the application. The sizing runs allows you to select the right hardware configuration to run the combined mode.

## Key Features

The following are the key features, see the combined Video Search and Summarization mode documentation for a baseline view of each:

- User-friendly and intuitive: You can use natural language through the easy-to-use interface to search.

- Optimized systems: The pipeline runs on Intel’s Edge AI systems, ensuring high performance, reliability, and low cost of ownership.

- Scalability: The pipeline can handle large volumes of video data, making it suitable for various applications, including media analysis, content management, and personalized recommendations.

- Enhanced user experience: You can find relevant content quickly and precisely through the summaries of important information.

- Reuse of building-block microservices: The pipeline manager microservice and inference microservices are reused between the different modes of Video Search and Summarization application. 

- Efficient indexing and retrieval: Reduces the computational and storage overhead by indexing summary embeddings instead of full-length video or frame-level embeddings, resulting in a faster search and lower resource usage.

- Contextual Relevance: Improves search quality by leveraging summaries that capture the core context and key events of each video, minimizing irrelevant results and reducing hallucinations.

- Unified pipeline orchestration: Seamlessly integrates search and summarization microservices, automating the workflow from video ingestion to summary generation, embedding creation, and semantic search. 

- Enhanced searchability: You can search within indexed summaries of important information.

- Efficient Summarization: You can generate summaries of videos and highlight key moments.

- Customizable: You can customize the pipeline, for example, to focus on particular topics or themes within the video, or to enable context extraction from audio, before embedding and indexing.

## High level architecture

The combined Video Search and Summarization mode uses all the components of the Video Search and Summarization application. The following figure shows the high-level architecture of the combined mode:

![System Architecture Diagram](./images/TEAI_VideoSearchSumm.drawio.svg)

The combined sample application:

- Demonstrates how Intel's Edge AI catalog of inference microservices can be used to build Video Search and Summarization pipelines quickly. The inference microservices are optimized for Intel's Edge AI systems.
  
- Serves as a blueprint for building similar scalable and modular solutions that can be deployed on Intel's Edge AI systems.
  
- Showcases the competitiveness of Intel's Edge AI systems to address varied deployment scenario requirements, from the edge to the cloud.
  
- Provides reference sample microservices for capabilities like video ingestion, embedding generation, vector search, and UI front end that reduces the effort to customize the application.

## How to Use the Application Effectively

The Video Search and Summarization pipeline offers features to improve accuracy for complex, long-form videos. 
Choosing which features to use involves balancing accuracy and performance. You can configure the pipeline based on answers to the following key questions, to determine the trade-off between accuracy and compute:

	1. How complex is the video?
	2. What is the pipeline's accuracy target, as measured by key qualitative metrics like the BERT score?
	3. What are the available compute resources for running the pipeline?
	4. What are the key performance metrics, for example, throughput, latency, and search response that the pipeline needs to achieve?
	5. What is the expected volume of the video collection and search query?

After configuring the pipeline, you can deploy the application, upload the video to be searched and summarized, set parameters like chunk duration and frame count, and then submit the request. The application updates you on the progress, provides the final summary, and adds the video to the searchable collection. The API specification outlines how to access the application’s features.

Detailed hardware and software requirements are available [here](./system-requirements.md).

To get started with the application, see the [Get Started](./get-started.md) page.
