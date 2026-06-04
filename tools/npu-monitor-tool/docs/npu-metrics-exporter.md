# Overview

NPU metrics exporter (npu-metrics-exporter.py) supports Prometheus data pull
model that stores time-series NPU metrics in its built-in database.

## Software Dependencies

```bash
pip install -r requirements-exporter.txt
```


## Start NPU Metrics Exporter
```bash
sudo env "PATH=$PATH" gunicorn -w 1 -b localhost:8000 npu-metrics-exporter:app
```
* __-w 1__: Start 1 working thread to service NPU metrics Restful server
* __-b localhost:8000__: Set 0.0.0.0 if want to allow any IP address.
  * Change __Port=8000__ according to your platform port allocation.

## Quick Test
```bash
$ curl http://localhost:8000/metrics
# HELP npu_monitor_temperature NPU Temperature [°C]
# TYPE npu_monitor_temperature gauge
npu_monitor_temperature{dev_id="0xad1d"} 35.0
# HELP npu_monitor_freq_hz DPU Frequency [Hz]
# TYPE npu_monitor_freq_hz gauge
npu_monitor_freq_hz{dev_id="0xad1d"} 1200.0000000000002
# HELP npu_memory_util NPU Memory Utilization [MB]
# TYPE npu_memory_util gauge
npu_memory_util{dev_id="0xad1d"} 292.140625
# HELP npu_memory_bandwidth NPU DDR Average Bandwidth [MB/s]
# TYPE npu_memory_bandwidth gauge
npu_memory_bandwidth{dev_id="0xad1d"} 9929.940412290676
# HELP npu_util NPU Utilization [%]
# TYPE npu_util gauge
npu_util{dev_id="0xad1d"} 80.0
# HELP npu_monitor_power NPU Power Consumption [Watts]
# TYPE npu_monitor_power gauge
npu_monitor_power{dev_id="0xad1d"} 1.6932698651519054
# HELP npu_tile_config NPU Tile Configuration
# TYPE npu_tile_config gauge
npu_tile_config{dev_id="0xad1d"} 2.0
```

# Prometheus
```bash
# Download and unpack the most recent Prometheus release
VERSION=3.11.0
$ wget https://github.com/prometheus/prometheus/releases/download/v${VERSION}/prometheus-${VERSION}.linux-amd64.tar.gz
$ tar -xvf prometheus-${VERSION}.linux-amd64.tar.gz
$ cd prometheus-${VERSION}.linux-amd64

# Configure Prometheus configuration for NPU Metrics
$ nano prometheus.yml
---
scrape_configs:
  - job_name: "NPU Metrics Exporter"
    scheme: http
    static_configs:
      - targets: ['localhost:8000']
---

# Start Prometheus
$ ./prometheus --config.file=./prometheus.yml
```

# Grafana Dashboard for NPU metrics
## Installation
```bash
# https://grafana.com/docs/grafana/latest/setup-grafana/installation/debian/
$ sudo mkdir -p /etc/apt/keyrings/
$ wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
$ echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
$ sudo apt-get update
$ sudo apt-get install grafana

# Add proxy setting in /etc/default/grafana-server
$ sudo cat << EOF > /etc/default/grafana-server
HTTP_PROXY=http://<PROXY_SERVER>:<PORT>
HTTPS_PROXY=http://<PROXY_SERVER>:<PORT>
NO_PROXY=localhost,127.0.0.1
EOF

# Enable and start Grafana server
$ sudo systemctl enable grafana-server
$ sudo systemctl restart grafana-server
$ sudo systemctl status grafana-server
```

## Open Grafana Webpage
- Connect to Grafana Server using http://localhost:3000
- Use initial login/password  = admin/admin
- Update Grafana server with new password

## Create Data-source for Prometheus
- From Grafana left navigation menu, select 'Connections/Data Sources'.
  Under "Add data source", search for "Prometheus" and select it.
- In the "Prometheus/Settings" tab:
  - Name = Prometheus Data Feeder
  - Prometheus server URL = http://localhost:9090
- Then, scroll to the bottom, click 'Save & test'.
- Confirm that above "Prometheus Data Feeder" is listed (created) under Data sources,
  when you select Grafana left navigation 'Connections/Data Sources' menu again.

## Create New Dashboard for NPU metrics
Import sample NPU metrics dashboard in [grafana-npu-dashboard.json](grafana-npu-dashboard.json)
