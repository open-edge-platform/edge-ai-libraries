# Custom Metrics Scripts

The easiest way to publish custom metrics without API calls or client libraries is to drop executable scripts into `/app/custom-metrics/`. Telegraf runs these scripts every 10 seconds and publishes their output directly to the Prometheus endpoint.

## How It Works

1. **Directory**: `/app/custom-metrics/` (inside the container)
2. **Interval**: Every 10 seconds, Telegraf executes all executable `*.sh` and `*.py` files
3. **Output**: Scripts print InfluxDB Line Protocol on stdout
4. **Result**: Metrics appear immediately on `:9273/metrics` (Prometheus format) and `/metrics/stream` (SSE)

The directory is persistent (mounted as a Docker volume), so scripts survive container restarts.

## Script Requirements

Each script must:

1. **Be executable**: `chmod +x your-script.sh`
2. **Print InfluxDB Line Protocol**: One metric per line on stdout
3. **Finish in <5 seconds**: Telegraf kills longer runs
4. **Produce clean output**: No debug prints, banners, or stderr
5. **Handle errors gracefully**: Non-zero exit codes don't crash Telegraf

## InfluxDB Line Protocol Format

```
measurement[,tag1=value1,tag2=value2] field1=value1[,field2=value2] [timestamp]
```

**Examples:**

```bash
# Simple metric with no tags
fan_speed rpm=2500i

# Metric with tags
cpu_temp,sensor=cpu0,location=socket1 temperature=65.5 1704067200000000000

# Multiple fields
system_load,host=myhost load1=1.23,load5=1.45,load15=1.67

# Without timestamp (Telegraf auto-assigns)
memory_usage,app=myapp used_mb=512i,total_mb=2048i
```

**Field types:**
- Integer: append `i` (`count=42i`)
- Float: no suffix (`temperature=65.5`)
- String: wrap in quotes (`status="running"`)
- Boolean: `t` or `f` (`enabled=t`)

## End-to-End Example: Fan RPM Metric

### Step 1: Start the Stack

```bash
docker compose up -d
```

### Step 2: Create the Script

Create a shell script that reads fan RPM and outputs InfluxDB Line Protocol:

```bash
docker exec metrics-manager sh -c 'cat > /app/custom-metrics/fan_rpm.sh << '"'"'EOF'"'"'
#!/bin/sh
# Read fan RPM from sysfs or use a simulation
# Example: read from /sys/class/hwmon/hwmon0/fan1_input (replace with your path)
rpm=$(awk "BEGIN{srand(); print int(2000+rand()*1000)}")
echo "fan_speed,sensor=cpu_fan,location=main rpm=${rpm}i"
EOF
chmod +x /app/custom-metrics/fan_rpm.sh'
```

Or use a Python script:

```bash
docker exec metrics-manager sh -c 'cat > /app/custom-metrics/fan_rpm.py << '"'"'EOF'"'"'
#!/usr/bin/env python3
import random
rpm = random.randint(2000, 3000)
print(f"fan_speed,sensor=cpu_fan,location=main rpm={rpm}i")
EOF
chmod +x /app/custom-metrics/fan_rpm.py'
```

### Step 3: Wait for the Next Telegraf Interval

Telegraf executes scripts every 10 seconds. Wait ~10 seconds, then verify the metric appeared:

```bash
curl -s http://localhost:9273/metrics | grep fan_speed
# Output: fan_speed_rpm{location="main",sensor="cpu_fan",host="..."} 2374
```

### Step 4: Verify in SSE Stream

The metric should appear in the live stream consumed by dashboards:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:9090/metrics/stream | grep fan_speed
```

### Step 5: Persist the Script on the Host (Optional)

Instead of inside the container's named volume, mount it from the host. Edit `compose.yaml`:

```yaml
services:
  metrics-manager:
    volumes:
      - ./my-scripts:/app/custom-metrics  # Replace default named volume
```

Then place your scripts in the local `./my-scripts/` directory and restart:

```bash
docker compose down
docker compose up -d
```

## Example Scripts

### CPU Load Average (Shell)

```bash
#!/bin/sh
# Read 1-minute, 5-minute, and 15-minute load averages
load=$(cat /proc/loadavg | awk '{print $1, $2, $3}')
set -- $load
echo "system_load,host=$(hostname) load1=$1,load5=$2,load15=$3"
```

### Process Count (Shell)

```bash
#!/bin/sh
# Count running processes
proc_count=$(ps aux | wc -l)
echo "process_count,host=$(hostname) count=$((proc_count-1))i"
```

### Custom Application Metric (Python)

```python
#!/usr/bin/env python3
import subprocess
import time

# Example: measure disk I/O
result = subprocess.run(['iostat', '-d', '1', '2'], capture_output=True, text=True)
lines = result.stdout.strip().split('\n')
last_line = lines[-1].split()

# Extract I/O reads/writes per second
reads_per_sec = float(last_line[1])
writes_per_sec = float(last_line[2])

print(f"disk_io,device=sda read_ops={reads_per_sec},write_ops={writes_per_sec}")
```

### Temperature Sensor (Python)

```python
#!/usr/bin/env python3
# Read CPU temperature from psutil library
import psutil

temps = psutil.sensors_temperatures()
if 'coretemp' in temps:
    core_temp = temps['coretemp'][0].current
    print(f"cpu_temperature,sensor=coretemp temperature={core_temp}")
else:
    print("cpu_temperature,sensor=fallback temperature=0")
```

## Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| Metric never appears on `:9273/metrics` | Script not executable, or stdout is not valid Influx Line Protocol | Run `docker exec metrics-manager /app/custom-metrics/your-script.sh` and inspect output. Add `set -x` to shell scripts for debug. |
| Telegraf log contains `metric parse error` | Script printed a non-Influx line (banner, debug output, etc.) | Ensure ONLY metric lines are printed to stdout. Redirect debug output to `/dev/null` or stderr. |
| Script appears to run only once | Misunderstanding of interval timing | The `[[inputs.exec]]` `interval = "10s"` runs every 10 seconds. Check logs: `docker logs metrics-manager \| grep telegraf` |
| Permission denied | Script lacks execute permission | Run `docker exec metrics-manager chmod +x /app/custom-metrics/your-script.sh` |
| Script times out after 5 seconds | Script takes too long | Optimize your script to finish faster, or increase the `timeout = "5s"` in `telegraf.conf` |

### Manual Testing

Test your script manually inside the container:

```bash
# List scripts in the custom-metrics directory
docker exec metrics-manager ls -la /app/custom-metrics/

# Run a script manually
docker exec metrics-manager /app/custom-metrics/fan_rpm.sh

# Check Telegraf logs for errors
docker logs metrics-manager | grep -i "metric\|exec\|telegraf"
```

---

## When NOT to Use `/app/custom-metrics`

Use the REST API instead when:

- **The metric originates inside an existing application** — push from your code with `POST /api/v1/metrics/simple`
- **You need sub-second granularity** — the `inputs.exec` interval is 10 seconds
- **The metric source already speaks OTLP or Influx Line Protocol over HTTP** — use `POST /api/v1/metrics/otlp` or `POST /api/v1/metrics/influx`

See [API Reference](../api-reference.md) for REST API options.

## Advanced: Extend supervisord with Custom Collectors

If you need a persistent background process (not just periodic scripts), add it to supervisord:

```ini
[program:my-collector]
command=/usr/local/bin/my-collector
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
priority=40
```

See [Configuration Guide](./environment-variables.md) for details on extending supervisord.

## Supporting Resources

- [Configuration Guide](./environment-variables.md)
- [API Reference](../api-reference.md)
- [Get Started Guide](../get-started.md)
- [Troubleshooting](../troubleshooting.md)

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
