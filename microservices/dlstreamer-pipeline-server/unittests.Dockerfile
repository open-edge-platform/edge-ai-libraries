ARG BASE_IMAGE=intel/dlstreamer-pipeline-server:2025.2.0-ubuntu22

FROM ${BASE_IMAGE} 

LABEL description="This Dockerfile is used to run unit tests for dlstreamer-pipeline-server microservice."

ARG USER

USER root

COPY ./tests/requirements.txt /home/pipeline-server/tests/requirements.txt
RUN pip3 install --no-cache-dir -r /home/pipeline-server/tests/requirements.txt

# Copy unit tests
COPY ./tests /home/pipeline-server/tests

USER ${USER}

