# Get Started

The GenAI Applications Sizing tool helps developers measure performance and resource consumption of Intel Edge AI GenAI sample applications. This guide will help you set up, run, and customize performance profiling for your GenAI workloads.

This guide shows how to:

- **Set up the profiling tool**: Install dependencies and configure the tool for your environment.
- **Run performance profiling**: Execute profiling for Chat Question and Answer (ChatQnA), ChatQnA Core, and Video Search and Summarization applications.
- **Collect resource metrics**: Capture CPU, GPU, memory, and other system metrics during profiling.
- **Customize profiling parameters**: Modify input profiles, request counts, and other settings to match your requirements.

## Prerequisites

- Verify that your target GenAI application is deployed and accessible.
- Install Docker tool: [Installation Guide](https://docs.docker.com/get-docker/) (for containerized execution).
- Install Python programming language v3.11 (for local execution).
- Install pip package manager.

## Project Structure

The repository is organized as follows:

```text
tools/genai-applications-sizing/
├── common/                    # Shared utilities
│   └── utils.py               # Common utility functions
├── data/                      # Sample input data
│   └── file.txt               # Sample text file for profiling
├── docs/                      # Documentation
│   └── user-guide/            # User guides and tutorials
├── profiles/                  # Configuration profiles
│   ├── profiles.yaml          # Input profiles definitions (videos, queries, prompts)
│   ├── chatqna-config.yaml    # Configuration for ChatQnA modular application
│   ├── chatqna-core-config.yaml # Configuration for ChatQnA Core application
│   ├── video-search-config.yaml # Configuration for Video Search profiling
│   └── video-summary-config.yaml # Configuration for Video Summary profiling
├── src/                       # Source code
│   ├── chat_question_and_answer/      # ChatQnA modular profiling
│   ├── chat_question_and_answer_core/ # ChatQnA Core profiling
│   └── video_search_and_summarization/ # Video Search/Summary profiling
├── Dockerfile                 # Docker image build file
├── profile-runner.py          # Main entry point script
├── requirements.txt           # Python dependencies
└── README.md                  # Project documentation
```

## Supported Applications

The tool supports performance profiling for the following GenAI applications:

| Application | Description | Config File |
|-------------|-------------|-------------|
| ChatQnA (Modular) | Chat Question and Answer with modular microservices | `profiles/chatqna-config.yaml` |
| ChatQnA Core | Chat Question and Answer Core application | `profiles/chatqna-core-config.yaml` |
| Video Search | Video indexing and semantic search | `profiles/video-search-config.yaml` |
| Video Summary | Video summarization | `profiles/video-summary-config.yaml` |

## Installation

### Option 1: Local Installation

1. Clone the repository and navigate to the project directory:

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   cd edge-ai-libraries/tools/genai-applications-sizing
   ```

2. Install the required Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

### Option 2: Docker Installation

1. Clone the repository and navigate to the project directory:

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   cd edge-ai-libraries/tools/genai-applications-sizing
   ```

2. Build the Docker image:

   ```bash
   docker build -t genai-sizing-tool .
   ```

## Run the Profiling Tool

### Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--app` | Application to profile: `chatqna`, `chatqna_core`, or `video_summary_search` | `chatqna` |
| `--input` | Path to configuration YAML file | `config.yaml` |
| `--host_ip` | IP address of the machine where the application is deployed | (required) |
| `--request_count` | Total number of requests to execute | `1` |
| `--users` | Number of concurrent users (currently fixed to 1 for single user profiling) | `1` |
| `--spawn_rate` | Rate at which users are spawned per second | `1` |
| `--collect_resource_metrics` | Enable collection of resource metrics (`yes` or `no`) | `no` |
| `--warmup_time` | Duration in seconds for warmup requests before performance testing | `0` |

### Running ChatQnA Profiling

Profile the Chat Question and Answer modular application:

```bash
python profile-runner.py \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --request_count=10 \
    --collect_resource_metrics=yes
```

### Running ChatQnA Core Profiling

Profile the Chat Question and Answer Core application:

```bash
python profile-runner.py \
    --app=chatqna_core \
    --input=profiles/chatqna-core-config.yaml \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --request_count=10 \
    --collect_resource_metrics=yes
```

### Running Video Search Profiling

Profile the Video Search application:

```bash
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-search-config.yaml \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --collect_resource_metrics=yes
```

### Running Video Summary Profiling

Profile the Video Summary application:

```bash
python profile-runner.py \
    --app=video_summary_search \
    --input=profiles/video-summary-config.yaml \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --collect_resource_metrics=yes \
    --warmup_time=60
```

### Running with Docker

```bash
docker run --rm \
    -v $(pwd)/reports:/app/reports \
    -v $(pwd)/data:/app/data \
    genai-sizing-tool \
    --app=chatqna \
    --input=profiles/chatqna-config.yaml \
    --host_ip=<IP_ADDRESS_OF_APP_DEPLOYED> \
    --request_count=10
```

## Configuration

### Global Configuration

Each configuration file contains a `global` section with common settings:

```yaml
global:
  report_dir: 'reports'              # Directory for output reports
  input_profiles_path: 'profiles/profiles.yaml'  # Path to input profiles
  perf_tool_repo: 'https://github.com/intel-retail/performance-tools.git'  # Performance tool repository
```

### API Configuration

Configure which APIs to test and their endpoints:

```yaml
apis:
  stream_log:
    enabled: true                    # Enable/disable this API test
    service_name: 'chatqna'          # Service name for reporting
    endpoints:
      chat: '8101/v1/chatqna/chat'   # Chat endpoint
      document: '8101/v1/dataprep/documents'  # Document endpoint
    input_profile: 'chatqna_wsf'     # Reference to input profile in profiles.yaml
```

### Input Profiles

Input profiles in `profiles/profiles.yaml` define test data and parameters:

```yaml
profiles:
  chatqna_wsf:
    input_type: "text"
    input_size: "small"
    files:
      - name: "file1.txt"
        path: "data/file1.txt"
    prompt: "Your test prompt here..."
    max_tokens: "1024"

  video_search_wsf:
    input_type: "video"
    input_size: "medium"
    files:
      - name: "video.mp4"
        path: "data/video.mp4"
    queries:
      - query: "Search query text..."
```

## Output Reports

After profiling completes, results are saved in the `reports` directory with timestamped folders:

```text
reports/
├── chatqna_modular_20260310_120000/
│   ├── perf_tool_logs         
│   └── chatqna/           
└── video_summary_search_20260310_130000/
    ├── perf_tool_logs/
    └── video_search/
```

## Resource Metrics Collection

When `--collect_resource_metrics=yes` is specified, the tool:

1. Clones the Intel Retail Performance Tools repository.
2. Starts system-level metric collection (CPU, GPU, memory, etc.).
3. Runs the profiling workload.
4. Stops collection and generates visualization graphs.

> **Note**: Resource metrics collection requires additional system permissions and may increase profiling overhead.

> **Important**: When using `--collect_resource_metrics=yes`, the sizing tool and the application being profiled must be running on the same machine. This ensures accurate measurement of system resources consumed by the application.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Verify the `--host_ip` is correct and the application is running |
| Missing input files | Ensure video/text files exist in the `data/` directory |
| Permission denied | Run with appropriate permissions or use Docker |
| Timeout errors | Increase `--warmup_time` for applications that need initialization |

## Supporting Resources

- [Chat Question and Answer Sample Application](../../sample-applications/chat-question-and-answer/README.md)
- [Chat Question and Answer Core Sample Application](../../sample-applications/chat-question-and-answer-core/README.md)
- [Video Search and Summarization Sample Application](../../sample-applications/video-search-and-summarization/README.md)
- [Locust Documentation](https://docs.locust.io/)
