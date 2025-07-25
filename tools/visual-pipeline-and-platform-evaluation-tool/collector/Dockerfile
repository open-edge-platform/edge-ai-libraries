FROM docker.io/library/rust:1.87 AS qmassa

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libudev-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN cargo install --locked qmassa

FROM docker.io/library/telegraf:1.32 AS collector

COPY --from=qmassa /usr/local/cargo/bin/qmassa /usr/local/bin/qmassa

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY qmassa_reader.py qmassa_reader.py
COPY read_cpu_freq.sh read_cpu_freq.sh
RUN chmod +x read_cpu_freq.sh

ENTRYPOINT ["/usr/bin/telegraf", "--config", "/etc/telegraf/telegraf.conf"]
