# Video Search and Summarization (VSS) Sample Application

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/sample-applications/video-search-and-summarization">
     GitHub project
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/sample-applications/video-search-and-summarization/README.md">
     Readme
  </a>
</div>
hide_directive-->

Use the Video Search and Summarization (VSS) sample application to search through your videos, summarize them, and more.

This foundational sample application provides three modes:

| Mode | Use To | Capability |
|---|---|---|
| Video Search ([overview](./how-it-works.md#video-search) and [how it works](./how-it-works/video-search.md)) | Find specific content within large video datasets through natural language. | Extract and index visual, audio, and textual features from video frames using the LangChain framework, multimodal embedding models, and agentic reasoning. Query using natural language or multi-modal models. |
| Video Summarization ([overview](./how-it-works.md#video-summarization) and [how it works](./how-it-works/video-summarization.md)) | Create concise summaries of long-form videos or live streams, automatically. | Improve searchability. Combine insights from different data types using Generative AI Vision Language Models (VLMs), computer vision, and audio analysis. |
| Combined Video Search and Summarization ([overview](./how-it-works.md#video-search-and-summarization) and [how it works](./how-it-works/video-search-and-summarization.md)) | Find specific content and create concise summaries of videos - ideal for a comprehensive video analysis. | Search quickly and directly over generated video summaries. Using the summary as a knowledge base makes the search results more relevant and accurate. |

The detailed documentation to help you get started, configure, and deploy the sample application
along with the required microservices are as follows.

## Quick Start

- **Get Started**
  - [Get Started](./get-started): How to get started with the sample application.
  - [System Requirements](./get-started/system-requirements.md): What hardware and software you need to run the sample application.

- **Deployment**
  - [How to Build from Source](./build-from-source.md): How to build from source code.
  - [How to Deploy with Helm](./deploy-with-helm.md): How to deploy using the Helm chart.

- **API Reference**
  - [API Reference](./api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](./release-notes.md): Information on the latest updates, improvements, and bug fixes.

<!--hide_directive
:::{toctree}
:hidden:

get-started
how-it-works
build-from-source
deploy-with-helm
directory-watcher-guide
api-reference
troubleshooting
release-notes
:::
hide_directive-->
