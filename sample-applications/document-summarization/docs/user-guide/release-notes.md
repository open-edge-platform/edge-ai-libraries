# Release Notes


## Current Release
**Version**: RC2 \
**Release Date**: WW26 2025 

**Key Features and Improvements:**

- **Document Summary Use Case:** The sample application provides capability to generate document summary using LlamaIndex Document Summary Index. It supports different file formats such as txt, pdf, docs.
- **Document Summary Unit Test Cases:** Unit tests for have been added along with readme containing steps to run these tests.
- **Helm:**  Helm chart integration is done to simplify the deployment and management of applications on Kubernetes clusters
- **Telemetry with Helm:** Along with docker now integrated with Helm too
- **Streamlined Build, Deployment and Documentation:** Added setup script to simplify service build and deployment processes and several other [user guide](../user-guide)  documents have been added
 
**Development Testing:**

Intel(R) Xeon(R) Platinum 8351N CPU @ 2.40GH
 
**Documentation:**

Documentation is **completed**. [README.md](../../README.md) is updated with installation steps and reference documents.  
 
**Github Branch:**
https://github.com/madhuri-rai07/edge-ai-libraries/tree/main/sample-applications/document-summarization
 
**Known Issues:**

- EMF Deployment package is not supported yet
- Summary time depends on the size and complexity (image, tables, cross references) of the document
 
**Additional Notes:**

Environment variables for the RC2 build are as follows:

```bash
export LLM_MODEL="microsoft/Phi-3.5-mini-instruct"
export VOLUME_OVMS=<model-path> # Ex: can be set to $PWD
```

## Previous releases

**Version**: RC1 \
**Release Date**: WW23 2025  

**Key Features and Improvements:**
- **Document Summary Use Case:** The sample application provides capability to generate document summary using LlamaIndex Document Summary Index. It supports different file formats such as txt, pdf, docs.
- **Nginx Support:** The app uses Nginx to expose the services and internal communication b/w the services happen over docker network.
- **Telemetry:** OpenTelemetry instrumentation provides the application insights and API traces
- **Streamlined Build, Deployment and Documentation:** Introduction of a setup script to simplify service build and deployment processes.
 
**Development Testing:**

Intel(R) Xeon(R) Platinum 8351N CPU @ 2.40GH
 
**Documentation:**

Readme.md is updated with installation steps. Complete documentation is WIP
 
**Github Branch:**
https://github.com/intel-innersource/applications.ai.intel-gpt.generative-ai-examples/blob/docsum_setup/sample-applications/document-summarization/
 
**Known Issues:**

N/A, documentation is WIP
 
**Additional Notes:**
Environment variables for the RC1 build are as follows:

```bash
1.	export LLM_MODEL="microsoft/Phi-3.5-mini-instruct"
2.	export VOLUME_OVMS=<model-path>
```