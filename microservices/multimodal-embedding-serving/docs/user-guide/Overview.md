# Multimodal Embedding Serving microservice
The Multimodal Embedding Serving microservice provides a scalable and efficient means to generate joint image and text embeddings using the CLIP model. It enables applications to perform cross-modal search, retrieval, and similarity tasks by exposing CLIP’s powerful vision-language understanding as a simple, production-ready service. 

# Overview
The microservice is a simple model serving to be able to do inference using CLIP model on a GPU or CPU hardware. It provides OpenAI standard API along with ability to deploy as a docker image or using Helm chart. 

> **Note:** The same Docker image and compose file can be used for both CPU and GPU deployments. Select the hardware by setting the appropriate environment variables as described in the [Get Started](get-started.md) guide.

# Supporting Resources

* [Get Started Guide](get-started.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
