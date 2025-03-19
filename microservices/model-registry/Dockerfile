FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get -y upgrade && apt-get install -y \
python3-opencv \
git \
software-properties-common \
curl

# Install Python 3.10 and pip 
# Set Python 3.10 as the default Python version
RUN add-apt-repository ppa:deadsnakes/ppa && apt-get install -y python3.10 \
python3.10-distutils python3-pip && update-alternatives --install /usr/bin/python python /usr/bin/python3.10 10

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
RUN sed -Ei 's/# deb-src /deb-src /' /etc/apt/sources.list
RUN apt-get update && \ 
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
RUN apt-get update && apt-get install wget -y

ENV PYTHONPATH $PYTHONPATH:/src

# Creates a non-root user with an explicit UID and adds permission to access the /src folder
RUN groupadd $MR_USER_NAME -g $MR_UID && \
    useradd -r -u $MR_UID -g $MR_USER_NAME $MR_USER_NAME && \
    chown -R $MR_USER_NAME /src

USER $MR_USER_NAME

# During debugging, this entry point will be overridden
CMD ["python", "main.py"]
