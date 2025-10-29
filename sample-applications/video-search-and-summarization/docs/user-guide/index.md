# Video Search and Summarization (VSS) Sample Application

Use the Video Search and Summarization (VSS) sample application to search through your videos, summarize them, and more.

This foundational sample application provides three modes:

| Mode | Use To | Capability |
|---|---|---|
| 🔍 Video Search ([overview](./overview-search.md) and [architecture](./overview-architecture-search.md)) | Find specific content within large video datasets through natural language. | Extract and index visual, audio, and textual features from video frames using the LangChain framework, multimodal embedding models, and agentic reasoning. Query using natural language or multi-modal models. |
| 📝 Video Summarization ([overview](./overview-summary.md) and [architecture](./overview-architecture-summary.md)) | Create concise summaries of long-form videos or live streams, automatically. | Improve searchability. Combine insights from different data types using Generative AI Vision Language Models (VLMs), computer vision, and audio analysis. |
| 🔗 Combined Video Search and Summarization ([overview](./overview-search-and-summary.md) and [architecture](./overview-architecture-search-and-summary.md)) | Find specific content and create concise summaries of videos - ideal for a comprehensive video analysis. | Search quickly and directly over generated video summaries. Using the summary as a knowledge base makes the search results more relevant and accurate. |

The detailed documentation to help you get started, configure, and deploy the sample application along with the required microservices are as follows.

## Documentation
  
- **Get Started**
  - [Get Started](./get-started): How to get started with the sample application.
  - [System Requirements](./system-requirements.md): What hardware and software you need to run the sample application.

- **Deployment**
  - [How to Build from Source](./build-from-source.md): How to build from source code.
  - [How to Deploy with Helm](./deploy-with-helm.md): How to deploy using the Helm chart.

- **API Reference**
  - [API Reference](./api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](./release-notes.md): Information on the latest updates, improvements, and bug fixes.

<!--hide_directive
:::{toctree}
:maxdepth: 2
:hidden:

Get Started <get-started>
overview-search
overview-summary
overview-search-and-summary
overview-architecture-search
overview-architecture-summary
overview-architecture-search-and-summary
build-from-source
deploy-with-helm
./directory-watcher-guide
api-reference
system-requirements
release-notes
:::
hide_directive-->
