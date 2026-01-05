# VLM OpenVINO serving microservice
The VLM OpenVINO serving is a microservice that provides a FastAPI based OpenVINO runtime serving supporting VLM models not supported yet in OpenVINO model serving. It is intended to perform inference over multi-modal VLM models by taking image and video as inputs. 

# Overview
The microservice is a simple model serving to be able to do inference using VLM models on a GPU or CPU hardware. It provides OpenAI standard chat completions API along with ability to deploy as a docker image or using Helm chart. 

## Models supported

| Model Name                          | Single Image Support | Multi-Image Support | Video Support | Hardware Support                |
|-------------------------------------|----------------------|---------------------|---------------|---------------------------------|
| Qwen/Qwen2-VL-2B-Instruct           | Yes                  | Yes                 | Yes           | CPU                             |
| OpenGVLab/InternVL2-4B              | Yes                  | No                  | No            | CPU                             |
| openbmb/MiniCPM-V-2_6               | Yes                  | No                  | No            | CPU                             |
| microsoft/Phi-3.5-vision-instruct   | Yes                  | Yes                 | No            | CPU, GPU(both single frame and multi-frame)                        |
| Qwen/Qwen2.5-VL-7B-Instruct         | Yes                  | Yes                 | Yes           | CPU, GPU(single frame only)     |
| Qwen/Qwen2.5-VL-3B-Instruct         | Yes                  | Yes                 | Yes           | CPU, GPU(single frame only)     |
| HuggingFaceTB/SmolVLM2-2.2B-Instruct| Yes                  | Yes                 | Yes           | CPU, GPU                        |

## Supporting Resources

* [Get Started Guide](get-started.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
