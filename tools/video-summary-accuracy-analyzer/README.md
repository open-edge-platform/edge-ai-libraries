# Video Summary Accuracy Analyzer

The Video Summary Accuracy Analyzer provides an offline evaluation framework for comparing machine-generated video summaries with ground-truth reference summaries. It combines lexical, semantic, factual consistency, and temporal coherence metrics to help developers assess summary quality through a web dashboard or REST APIs.

The analyzer includes a FastAPI evaluation service, a Gradio dashboard, and an NGINX gateway. It can evaluate complete summary files or calculate individual BERTScore, ROUGE, semantic similarity, and factual consistency metrics.

## Documentation

- **Getting Started**
  - [Get Started](./docs/user-guide/get-started.md): Deploy and test the application with Docker Compose.
  - [How to Build from Source](./docs/user-guide/build-from-source.md): Build the backend and UI container images from source.

See [Get Started](./docs/user-guide/get-started.md) for detailed setup and usage instructions.

## Additional Links

- [Edge AI Libraries](../..)
- [Issues](https://github.com/open-edge-platform/edge-ai-libraries/issues)
- [Pull Requests](https://github.com/open-edge-platform/edge-ai-libraries/pulls)
