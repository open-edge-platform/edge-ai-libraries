# Video Search and Summarization (VSS) Sample Application

Use the Video Search and Summarization (VSS) sample application to search through your videos, summarize them, and more.

This foundational sample application provides four deployment modes:

| Mode | Setup Command | Usage | Capability |
|---|---|---|---|
| 📝 Summary | `source setup.sh --summary` | Create concise summaries of long-form videos or live streams, automatically. | Combine insights from different data types using Generative AI Vision Language Models (VLMs), computer vision, and audio analysis. |
| 🔍 Search | `source setup.sh --search` | Find specific content within large video datasets through natural language. | Extract and index visual, audio, and textual features from video frames using multimodal embedding models. Query using natural language. |
| 🔀 Dual UI | `source setup.sh --summary --search` | Run summarization and search side-by-side with separate UIs. | Both summary and search capabilities with independent UI instances. |
| 🔗 Unified UI | `source setup.sh --summary-and-search` | Create summaries of videos and search for specific content in a single unified UI. | Search over video summary's text embeddings for more relevant results. |


## Why Use VSS?

- **Data privacy**: Local processing ensures your data stays private.
- **Ease of use**: You can search using natural language.
- **Improved accuracy**: Multi-modal analysis works on video, audio, and text at the same time, which improves the results.
- **Scalability**: You can work on one or multiple videos automatically.

The detailed documentation to help you get started, configure, and deploy the sample application along with the required microservices are as follows.

## Documentation

- **Get Started**
  - [Get Started](./docs/user-guide/get-started.md): How to get started with the sample application.
  - [System Requirements](./docs/user-guide/get-started/system-requirements.md): What hardware and software you need to run the sample application.

- **Deployment**
  - [How to Build from Source](./docs/user-guide/build-from-source.md): How to build from source code.
  - [How to Deploy with Helm](./docs/user-guide/deploy-with-helm.md): How to deploy using the Helm chart.

- **AI Agent Integration**
  - [MCP Server](./docs/user-guide/mcp-server.md): Connect AI agents to VSS Search using the Model Context Protocol (MCP).

- **API Reference**
  - [API Reference](./docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](./docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.
