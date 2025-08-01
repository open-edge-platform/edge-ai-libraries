ARG BASE_IMAGE=ghcr.io/open-edge-platform/edge-ai-libraries/intel/edge-ai-dlstreamer:20250729_EAL1.2_DLS_RC2-ubuntu22

FROM ${BASE_IMAGE} 

LABEL description="This Dockerfile is used to run unit tests for dlstreamer-pipeline-server microservice."

ARG USER

USER root

COPY ./tests/requirements.txt /home/pipeline-server/tests/requirements.txt
RUN pip3 install --no-cache-dir -r /home/pipeline-server/tests/requirements.txt

# Copy unit tests
COPY ./tests /home/pipeline-server/tests

USER ${USER}