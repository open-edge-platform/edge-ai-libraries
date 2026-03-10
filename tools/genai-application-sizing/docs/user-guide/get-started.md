# Get Started with Generative AI Hardware Sizing Tool

This guide will help you quickly set up and run the Generative AI Hardware Sizing Tool to benchmark and profile your GenAI applications on Intel hardware.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running the Tool](#running-the-tool)
- [Understanding Results](#understanding-results)
- [Common Use Cases](#common-use-cases)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

#### Hardware
- **CPU**: Intel processor (recommended for optimal performance)
- **RAM**: Minimum 8GB, 16GB+ recommended for video processing
- **Storage**: At least 10GB free space for reports and dependencies
- **Network**: Access to target GenAI application server

#### Software
- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **Python**: Version 3.11 or higher
- **Docker**: Latest version (required only if collecting resource metrics)
- **Git**: For cloning performance tools repository

### Target Application Requirements

Before running the tool, ensure you have:

1. **A deployed GenAI application** with one of the following:
   - ChatQnA (Question-Answering) service
   - Video Summary and Search service
   
2. **Network accessibility** to the application server
   
3. **API endpoint information**:
   - Server IP address or hostname
   - Port numbers for each API endpoint
   - API paths (e.g., `/v1/chatqna/chat`)

### Verify Prerequisites

```bash
# Check Python version (should be 3.11+)
python3 --version

# Check Docker installation (only needed for resource metrics)
docker --version

# Check Git
git --version

# Verify network connectivity to your application
# Replace <IP> and <PORT> with your values
curl http://<IP>:<PORT>/health
```

---

## Installation

### Option 1: Local Installation (Recommended)

#### Step 1: Clone or Navigate to the Repository

```bash
cd /path/to/generative-ai-hardware-sizing
```

#### Step 2: Create Python Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Your prompt should now show (venv)
```

#### Step 3: Install Dependencies

```bash
# Install required Python packages
pip install -r requirements.txt

# Verify installation
pip list | grep locust
```

Expected output should include:
```
locust==2.42.5
locust-plugins==5.0.0
```

### Option 2: Docker Installation

If you prefer containerized execution:

```bash
# Build Docker image
docker build -t genai-hw-sizing:latest .

# Verify image creation
docker images | grep genai-hw-sizing
```

---

## Quick Start

### 1. Prepare Your Test Data

Place your test files in the `data/` directory:

```bash
# For ChatQnA testing
cp /path/to/your/documents/*.txt data/

# For Video testing
cp /path/to/your/videos/*.mp4 data/

# Verify files are copied
ls -lh data/
```

### 2. Update Configuration Files

Edit the configuration file for your application type:

**For ChatQnA:**
```bash
nano profiles/chatqna-config.yaml
```

Update the following:
```yaml
apis:
  stream_log:
    enabled: true
    service_name: 'chatqna'
    endpoints:
      chat: '8101/v1/chatqna/chat'          # Change port if needed
      document: '8101/v1/dataprep/documents' # Change port if needed
    input_profile: 'stream_log_medium_text'
```

**For Video Search:**
```bash
nano profiles/video-search-config.yaml
```

Update the following:
```yaml
apis:
  video_search:
    enabled: true
    service_name: 'search'
    endpoints:
      upload: '12345/manager/videos'         # Update with actual port
      search: '12345/manager/search'         # Update with actual port
      embedding: '12345/manager/videos/search-embeddings'
    input_profile: 'video_search_multiple'
```

### 3. Run Your First Test

**Simple ChatQnA test with 1 user:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run benchmark
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --users=1 \
    --request_count=5 \
    --host_ip=<YOUR_APP_IP> \
    --collect_resource_metrics=no
```

Replace `<YOUR_APP_IP>` with your application server's IP address (e.g., `192.168.1.100`).

### 4. Check Results

Results are saved in the `reports/` directory with a timestamp:

```bash
# List generated reports
ls -la reports/

# View the latest report
cd reports/chatqna_modular_<timestamp>/
ls -la

# View summary metrics
cat chat/chat_api_summary_metrics.csv
```

---

## Configuration

### Understanding Configuration Files

The tool uses two types of configuration files:

1. **profiles.yaml** - Defines test input profiles (prompts, queries, video files)
2. **Application config** - Defines API endpoints and settings (e.g., `chatqna-config.yaml`)

### Customizing Input Profiles

Edit `profiles/profiles.yaml` to create custom test scenarios:

```yaml
profiles:
  # Custom ChatQnA profile
  my_custom_chat:
    input_type: "text"
    input_size: "small"
    files:
      - name: "intel_docs.txt"
        path: "data/intel_docs.txt"
    prompt: "What are the key features of Intel processors?"
    max_tokens: "1024"
  
  # Custom Video profile
  my_custom_video:
    input_type: "video"
    input_size: "single"
    files:
      - name: "demo_video.mp4"
        path: "data/demo_video.mp4"
    queries:
      - "Find scenes with people talking"
      - "Show me outdoor scenes"
```

### Configuring API Endpoints

Each application config file has a similar structure:

```yaml
global:
  report_dir: 'reports'
  input_profiles_path: 'profiles/profiles.yaml'
  perf_tool_repo: 'https://github.com/intel-retail/performance-tools.git'

apis:
  api_name:
    enabled: true/false          # Enable or disable this API
    service_name: 'service'      # Service name for logging
    endpoints:
      endpoint_type: 'port/path' # Format: 'PORT/PATH'
    input_profile: 'profile_name' # Reference from profiles.yaml
```

**Important**: Always update the port numbers to match your deployed application.

---

## Running the Tool

### Command Line Arguments

```bash
python profile-runner.py [OPTIONS]
```

**Available Options:**

| Argument | Description | Default | Required |
|----------|-------------|---------|----------|
| `--app` | Application to test: `chatqna`, `chatqna_core`, `video_summary_search` | `chatqna` | Yes |
| `--input` | Path to configuration YAML file | `config.yaml` | Yes |
| `--host_ip` | IP address of the application server | `""` | Yes |
| `--users` | Number of concurrent users to simulate | `1` | No |
| `--request_count` | Total requests per user | `1` | No |
| `--spawn_rate` | Users spawned per second | `1` | No |
| `--collect_resource_metrics` | Collect CPU/GPU/NPU metrics: `yes` or `no` | `no` | No |

### Example Commands

#### 1. ChatQnA - Single User Test
```bash
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --users=1 \
    --request_count=10 \
    --host_ip=192.168.1.100 \
    --collect_resource_metrics=no
```

#### 2. ChatQnA - Load Test (10 Concurrent Users)
```bash
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --users=10 \
    --request_count=5 \
    --spawn_rate=2 \
    --host_ip=192.168.1.100 \
    --collect_resource_metrics=yes
```

#### 3. Video Summary Test
```bash
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-summary-config.yaml \
    --users=1 \
    --request_count=3 \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --collect_resource_metrics=yes
```

#### 4. Video Search Test
```bash
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-search-config.yaml \
    --users=1 \
    --request_count=20 \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --collect_resource_metrics=yes
```

#### 5. Using Docker
```bash
docker run -it --network host \
    -v $(pwd)/profiles:/app/profiles \
    -v $(pwd)/data:/app/data \
    -v $(pwd)/reports:/app/reports \
    genai-hw-sizing:latest \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --users=5 \
    --request_count=10 \
    --host_ip=192.168.1.100
```

### Understanding Load Parameters

**Users and Requests:**
- `--users=10 --request_count=5` = 10 concurrent users × 5 requests each = **50 total requests**
- Requests are executed concurrently based on spawn rate

**Spawn Rate:**
- `--spawn_rate=2` = Add 2 new users per second
- With `--users=10`, it takes 5 seconds to spawn all users
- Lower spawn rate = gradual ramp-up (more realistic)
- Higher spawn rate = immediate load (stress test)

**Resource Metrics:**
- `--collect_resource_metrics=yes`:
  - Clones performance-tools repository
  - Starts Docker container to collect metrics
  - Monitors CPU, GPU, NPU, memory usage
  - Generates visualization graphs
  - **Note**: Requires Docker to be running

---

## Understanding Results

### Report Directory Structure

After running a test, reports are generated in a timestamped directory:

```
reports/
└── chatqna_modular_20251125_125955/
    ├── chat/
    │   ├── chat_api_individual_metrics.json
    │   ├── chat_api_summary_metrics.csv
    │   └── responses/
    │       ├── chat_response_1.txt
    │       ├── chat_response_2.txt
    │       └── ...
    │
    ├── document/
    │   └── document_api_metrics.json
    │
    └── perf_tool_logs/              (if resource metrics enabled)
        ├── npu_usage.csv
        ├── pcm.csv
        ├── qmassa1-56a0-i915-parsed.json
        ├── qmassa1-56a0-i915-tool-generated.json
        └── usage_graph.png
```

### Key Metrics Files

#### 1. Summary Metrics (CSV)

**File**: `chat/chat_api_summary_metrics.csv`

```csv
Metric,Avg,Min,Max,p99,p90,p75
Request Latency (ms),2450.3,1823.1,3156.8,3089.5,2876.2,2634.7
Time to First Token (ms),435.2,327.4,578.9,562.3,512.6,478.1
Inter Token Latency (ms),24.8,19.7,33.5,32.1,29.4,27.3
Tokens Per Second,40.3,29.8,50.6,47.2,44.1,42.0
Input Tokens,185.5,150,220,215,205,195
Output Tokens,1542.3,1200,1850,1820,1680,1600
Throughput,4.2,NA,NA,NA,NA,NA
```

**What it means:**
- **Request Latency**: Total time from request to complete response
- **Time to First Token (TTFT)**: How long users wait before seeing first output
- **Inter Token Latency (ITL)**: Smoothness of streaming (lower is better)
- **Tokens Per Second (TPS)**: Token generation speed
- **Throughput**: Requests processed per second
- **p99, p90, p75**: Percentile values (e.g., p99 = 99% of requests faster than this)

#### 2. Individual Metrics (JSON)

**File**: `chat/chat_api_individual_metrics.json`

Contains detailed metrics for each request:
```json
[
  {
    "request_number": 1,
    "latency_ms": 2345.6,
    "ttft_ms": 423.1,
    "itl_ms": 25.3,
    "tps": 39.5,
    "input_tokens": 180,
    "output_tokens": 1520,
    "response_saved": "chat_response_1.txt"
  },
  ...
]
```

#### 3. Resource Metrics (if enabled)

**File**: `perf_tool_logs/npu_usage.csv`

Contains CPU, GPU, NPU utilization over time:
```csv
timestamp,cpu_usage_%,gpu_usage_%,npu_usage_%,memory_mb
2025-11-25 12:59:56,45.2,78.3,12.5,8456
2025-11-25 12:59:57,47.8,82.1,15.3,8523
...
```

**Graphs**: `usage_graph.png` visualizes these metrics over time.

### Video-Specific Metrics

For video summary/search tests:

**File**: `summary/summary_api_metrics_summary.csv`
```csv
Metric,Avg,Min,Max,p99,p90,p75
Video Upload Time (s),12.3,10.5,15.8,15.2,14.1,13.5
Time to First Frame Summary (s),8.5,7.2,10.3,9.8,9.1,8.9
Video Summarization Duration (s),45.6,38.2,56.7,54.3,50.2,48.1
Summarization FPS,2.5,2.1,3.0,2.9,2.7,2.6
Video Duration (s),120.5,115,125,124,123,122
Video Size (MB),85.3,78,92,90,88,86
```

---

## Common Use Cases

### Use Case 1: Initial Performance Baseline

**Goal**: Understand single-user performance

```bash
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --users=1 \
    --request_count=20 \
    --host_ip=192.168.1.100 \
    --collect_resource_metrics=yes
```

**What to look for:**
- Average TTFT: Should be < 500ms for good UX
- ITL: Should be < 50ms for smooth streaming
- Resource usage: Identify bottlenecks (CPU vs GPU)

### Use Case 2: Hardware Sizing for Production

**Goal**: Determine hardware needed for target concurrency

```bash
# Test increasing load
for users in 1 5 10 20 50; do
    echo "Testing with $users concurrent users..."
    python profile-runner.py \
        --app=chatqna \
        --input=profiles/chatqna-config.yaml \
        --users=$users \
        --request_count=10 \
        --spawn_rate=5 \
        --host_ip=192.168.1.100 \
        --collect_resource_metrics=yes
    
    sleep 120  # Cool-down period
done
```

**What to look for:**
- At what concurrency does latency degrade?
- When does GPU/CPU reach 100% utilization?
- What's the maximum throughput?

### Use Case 3: Comparing Model Performance

**Goal**: Compare different LLM models or configurations

```bash
# Test Model A
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-model-a.yaml \
    --users=10 \
    --request_count=10 \
    --host_ip=192.168.1.100

# Switch to Model B on server, then:
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-model-b.yaml \
    --users=10 \
    --request_count=10 \
    --host_ip=192.168.1.100
```

**Compare:**
- TPS (throughput)
- TTFT (responsiveness)
- Resource usage (efficiency)

### Use Case 4: Video Processing Pipeline Optimization

**Goal**: Optimize video summarization parameters

```bash
# Edit profiles.yaml to test different sampling rates
# Test 1: High frame sampling (more accurate, slower)
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-summary-high-quality.yaml \
    --users=1 \
    --request_count=5 \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED>

# Test 2: Low frame sampling (faster, less accurate)
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-summary-fast.yaml \
    --users=1 \
    --request_count=5 \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED>
```

**Compare:**
- Summarization FPS
- Total processing time
- Quality vs speed tradeoff

---

## Troubleshooting

### Issue 1: Connection Refused

**Error:**
```
Connection refused to http://<IP>:<PORT>
```

**Solutions:**
```bash
# 1. Verify application is running
curl http://<IP>:<PORT>/health

# 2. Check if port is open
telnet <IP> <PORT>

# 3. Verify firewall rules
sudo ufw status

# 4. Check application logs on the server
```

### Issue 2: Module Not Found

**Error:**
```
ModuleNotFoundError: No module named 'locust'
```

**Solutions:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep locust
```

### Issue 3: Docker Permission Denied

**Error:**
```
docker: permission denied while trying to connect
```

**Solutions:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Log out and log back in, or:
newgrp docker

# Verify
docker ps
```

### Issue 4: Performance Tool Fails to Start

**Error:**
```
Failed to clone performance-tools repository
```

**Solutions:**
```bash
# Check network connectivity
ping github.com

# Manually clone the repo
cd /tmp
git clone https://github.com/intel-retail/performance-tools.git

# Run without resource metrics
python profile-runner.py ... --collect_resource_metrics=no
```

### Issue 5: Out of Memory During Video Processing

**Error:**
```
MemoryError: Unable to allocate array
```

**Solutions:**
```bash
# 1. Process fewer videos at once
# Edit profiles.yaml to reduce file count

# 2. Use smaller video files for testing

# 3. Increase system swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 4. Reduce sampling parameters in payload
```

### Issue 6: Slow Response Times

**Possible Causes:**
1. **Network latency**: Run tool closer to application server
2. **Cold start**: First request is always slower (exclude from analysis)
3. **Resource contention**: Other processes using CPU/GPU
4. **Application not optimized**: Check application logs

**Debug:**
```bash
# Check network latency
ping -c 10 <IP>

# Monitor system resources
htop

# Check application resource usage on server
```

### Getting Help

**Enable verbose logging:**
```bash
# Add to beginning of profile-runner.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check logs:**
```bash
# Run with output redirected
python profile-runner.py ... 2>&1 | tee debug.log

# Review the log
less debug.log
```

**Common log files:**
- Locust logs: stdout (redirect to file)
- Performance tools: `reports/<timestamp>/perf_tool_logs/`
- Docker logs: `docker logs <container_id>`

---

## Next Steps

Now that you've got started:

1. **Review the full documentation**: See `overview.md` for detailed architecture
2. **Customize profiles**: Create profiles matching your use cases
3. **Run comprehensive tests**: Test various load scenarios
4. **Analyze results**: Use metrics to optimize your deployment
5. **Automate testing**: Create scripts for CI/CD integration

## Additional Resources

- **Repository**: Full source code and examples
- **Requirements**: See `requirements.txt` for dependencies
- **Docker**: See `Dockerfile` for containerized setup
- **Profiles**: See `profiles/` directory for example configurations

---

## Quick Reference

### Essential Commands

```bash
# Activate environment
source venv/bin/activate

# Simple test
python profile-runner.py --app=chatqna --input=profiles/chatqna-config.yaml --users=1 --host_ip=<IP>

# Load test
python profile-runner.py --app=chatqna --input=profiles/chatqna-config.yaml --users=10 --request_count=10 --host_ip=<IP> --collect_resource_metrics=yes

# Video test
python profile-runner.py --app=video_summary_search --input=profiles/video-search-config.yaml --users=1 --host_ip=<IP> --collect_resource_metrics=yes

# View results
ls -la reports/
cat reports/<latest>/chat/chat_api_summary_metrics.csv
```

### File Locations

- **Test data**: `data/`
- **Configurations**: `profiles/`
- **Results**: `reports/`
- **Source code**: `src/`
- **Main script**: `profile-runner.py`

---

**Happy Benchmarking! 🚀**
