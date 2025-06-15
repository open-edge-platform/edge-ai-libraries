FROM intel/dlstreamer-pipeline-server:3.1.0-ubuntu22
LABEL description="This Dockerfile is used to run unit tests for dlstreamer-pipeline-server microservice."

COPY ./tests/requirements.txt /home/pipeline-server/tests/requirements.txt
RUN pip3 install --no-cache-dir -r /home/pipeline-server/tests/requirements.txt

# Copy unit tests
COPY ./tests /home/pipeline-server/tests