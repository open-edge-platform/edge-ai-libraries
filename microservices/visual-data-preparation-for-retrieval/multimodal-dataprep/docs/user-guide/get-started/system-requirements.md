# System Requirements

This page provides detailed hardware, software, and platform requirements to help you set up
and run the microservice efficiently.

## Supported Platforms

This microservice currently supports CPU, GPU, and NPU based runs. This microservice is
intended to run in the context of video summary pipeline. Hence, supported platform, OS
configuration, etc., is as per the documentation in the sample application. The documentation
here does not provide separate requirements.

**Operating Systems**:

- As per sample application documentation:
  - [Video Search and Summarization System Requirements](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/get-started/system-requirements.html#operating-systems-used-for-validation)
  - [Visual Search and Q&A System Requirements](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/visual-search-question-and-answering/get-started/system-requirements.html#supported-platforms)

**Hardware Platforms**:

- As per sample application documentation:
  - [Video Search and Summarization System Requirements](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/get-started/system-requirements.html#hardware-platforms-used-for-validation)
  - [Visual Search and Q&A System Requirements](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/visual-search-question-and-answering/get-started/system-requirements.html#supported-platforms)

## Minimum Requirements

- As per sample application documentation:
  - [Video Search and Summarization System Requirements](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/get-started/system-requirements.html#minimum-configuration)
  - [Visual Search and Q&A System Requirements](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/visual-search-question-and-answering/get-started/system-requirements.html#minimum-requirements)

## Software Requirements

**Required Software**:

- Docker 24.0
- Python 3.10
- MinIO server (optional, for object storage)
- If you are behind a proxy, please make sure `http_proxy`, `https_proxy`, `no_proxy` are properly set on the shell you use.

## Validation

- Ensure all required software are installed and configured before proceeding to [Get Started](../get-started.md).

## Supporting Resources

- [Overview](../index.md)
- [API Reference](../api-reference.md)
