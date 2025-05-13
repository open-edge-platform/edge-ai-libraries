FROM ubuntu:20.04
ENV DEV_ROOT=/app
ENV XDG_CACHE_HOME=/app
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR ${DEV_ROOT}
COPY requirements.txt ${DEV_ROOT}/requirements.txt

# install telegraf & intel-gpu-tools (which includes intel_gpu_top)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    sudo vim curl unzip git lsof wget \
    python3 python3-dev python3-pip \
    gnupg supervisor \
    linux-tools-common linux-tools-generic linux-cloud-tools-generic \
    build-essential pkg-config libfontconfig-dev libudev-dev \
    jq libcap2-bin && \
    # Add InfluxData GPG key and repo
    curl -s https://repos.influxdata.com/influxdata-archive.key -o influxdata-archive.key && \
    echo '943666881a1b8d9b849b74caebf02d3465d6beb716510d86a39f6c8e8dac7515 influxdata-archive.key' | sha256sum -c - && \
    gpg --dearmor < influxdata-archive.key > /etc/apt/trusted.gpg.d/influxdata-archive.gpg && \
    echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive.gpg] https://repos.influxdata.com/debian stable main' > /etc/apt/sources.list.d/influxdata.list && \
    rm influxdata-archive.key && \
    apt-get update && \
    apt-get install -y --no-install-recommends telegraf && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    # Install Python requirements
    python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache-dir -r ${DEV_ROOT}/requirements.txt


# Install rustup
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y 

# Configure cargo
ENV PATH="/root/.cargo/bin:${PATH}"

# Install qmassa
RUN cargo install --locked qmassa


COPY ./supervisord.conf /etc/supervisor/conf.d/supervisord.conf

COPY qmassa_reader.py ${DEV_ROOT}/qmassa_reader.py
COPY read_cpu_freq.sh ${DEV_ROOT}/read_cpu_freq.sh
RUN chmod +x ${DEV_ROOT}/read_cpu_freq.sh
EXPOSE 7005
ENV PORT=7005


ENTRYPOINT ["/usr/bin/supervisord"]
