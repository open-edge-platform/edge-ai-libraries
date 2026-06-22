FROM docker.io/library/rust:1.87 AS qmassa

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libudev-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install qmassa directly from its GitHub repository by tag instead of from
# crates.io. The version is pinned so the build keeps working on this image's
# Rust toolchain (rust:1.87); installing from a git tag also avoids build
# failures if a crates.io version is ever yanked by the upstream maintainer.
RUN cargo install --locked --git https://github.com/ulissesf/qmassa --tag v1.0.0

FROM docker.io/library/telegraf:1.35.3 AS collector

COPY --from=qmassa /usr/local/cargo/bin/qmassa /usr/local/bin/qmassa

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY telegraf.conf /etc/telegraf
COPY qmassa_reader.py qmassa_reader.py
COPY read_cpu_freq.sh read_cpu_freq.sh
RUN chmod +x read_cpu_freq.sh

# nosemgrep: missing-user-entrypoint
ENTRYPOINT ["/usr/bin/telegraf", "--config", "/etc/telegraf/telegraf.conf"]
