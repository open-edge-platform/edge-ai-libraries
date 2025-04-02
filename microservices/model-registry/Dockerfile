FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Update and install necessary packages
RUN apt-get update && apt-get -y upgrade && \
    apt-get install -y --no-install-recommends \
    git \
    software-properties-common \
    curl \
    wget \
    python3.10 \
    python3.10-venv \
    python3-pip \
    python3.10-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create symbolic links for python and pip commands
RUN ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

EXPOSE 80

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

# Store Source code for relevant dependencies
WORKDIR /third_party
RUN sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python3-opencv && \
    apt-get source --download-only -q git && \
    tar -cvf debian_deps.tar.xz * && \
    rm -rf git* && \
    pip wheel --wheel-dir=. --no-deps psycopg2-binary==2.9.7 && \
    tar -cvf python_deps.tar.xz psycopg2_binary* && \
    rm -rf psycopg2_binary*

COPY ./third_party_deb_apk_deps.txt /third_party
COPY ./third-party-programs.txt /third_party

WORKDIR /src
COPY ./src /src

ARG MR_UID
ARG MR_USER_NAME

ENV PYTHONPATH $PYTHONPATH:/src

# Creates a non-root user with an explicit UID and adds permission to access the /src folder
RUN groupadd $MR_USER_NAME -g $MR_UID && \
    useradd -r -u $MR_UID -g $MR_USER_NAME $MR_USER_NAME && \
    chown -R $MR_USER_NAME /src

USER $MR_USER_NAME

ENV SERVER_IP_ADDRESS 0.0.0.0

# During debugging, this entry point will be overridden
CMD ["python", "main.py"]
