# Traffic Data Analysis Workflow

## Overview

The Scene Intelligence microservice employs a sophisticated multi-stage traffic analysis pipeline that combines real-time directional traffic monitoring with AI-powered Vision Language Model (VLM) analysis. This document explains the complete workflow, configuration parameters, and data retention policies.

## Table of Contents

- [Traffic Analysis Pipeline](#traffic-analysis-pipeline)
- [VLM Integration and Triggers](#vlm-integration-and-triggers)
- [Windowed Analysis System](#windowed-analysis-system)
- [Concurrency and Performance](#concurrency-and-performance)
- [Configuration Parameters](#configuration-parameters)
- [Data Retention and Persistence](#data-retention-and-persistence)
- [API Integration](#api-integration)
- [Troubleshooting](#troubleshooting)

## Traffic Analysis Pipeline

### 1. Data Collection

```
Video Streams → DL Streamer → MQTT Messages → Scene Intelligence Service
```

The pipeline starts with video streams from intersection cameras, processed by DL Streamer to detect vehicles and pedestrians, then transmitted via MQTT as region count data.

### 2. Directional Traffic Calculation

**File**: `src/scene_intelligence/services/directional_traffic_service.py`

Traffic is calculated using predefined region mappings:

```python
TRAFFIC_FORMULAS = {
    'northbound': ['NBLANE', 'WBNBRTLANE', 'EBNBLTLANE'],
    'southbound': ['SBLANE', 'WBSBLTLANE', 'EBSBRTLANE'],  
    'eastbound': ['EBLANE', 'NBEBRTLANE', 'SBEBLTLANE'],
    'westbound': ['WBLANE', 'NBWBLTLANE']
}
```

**Process**:

1. MQTT service receives region count data
2. Maps scene UUIDs to intersection IDs
3. Calculates directional densities using region formulas
4. Stores current traffic state per intersection

### 3. VLM Analysis Decision Engine

**File**: `src/scene_intelligence/services/vlm_service.py`

The VLM system analyzes high-density traffic situations using a multi-gated approach.

## VLM Integration and Triggers

### Trigger Conditions (ALL must be true)

#### 1. **Threshold Gate**: Traffic Density Exceeds Threshold

```python
# Configurable via environment or config file
high_density_threshold = 5.0  # Default

# Any direction must exceed threshold
directional_densities = {
    "northbound": 6.2,  # ✅ Exceeds threshold
    "southbound": 3.1,
    "eastbound": 2.8,
    "westbound": 1.5
}
```

**Configuration**:

- **Environment**: `HIGH_DENSITY_THRESHOLD=5.0`
- **Config File**: `config/vlm_config.json` → `traffic_analysis.high_density_threshold`

#### 2. **State Change Gate**: Normal → High Traffic Transition

```python
# Only triggers on state transitions, not continuous high traffic
if previous_state == NORMAL and current_state == HIGH:
    record_state_change_time()
    # Continue to next gate
```

**Purpose**: Prevents continuous VLM calls during sustained high traffic periods.

#### 3. **Persistence Gate**: Sustained High Traffic Duration

```python
# Traffic must remain high for minimum duration
minimum_duration = 30  # seconds (configurable)
time_in_high_state = now - state_change_time

if time_in_high_state >= minimum_duration:
    # Continue to next gate
```

**Configuration**:

- **Environment**: `MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=30`
- **Config File**: `traffic_analysis.minimum_duration_for_consistently_high_traffic_seconds`

#### 4. **Cooldown Gate**: Time Since Last Analysis

```python
# Prevent frequent VLM calls for same intersection
cooldown_minutes = 1  # Default
time_since_last = now - last_vlm_analysis_time

if time_since_last >= cooldown_minutes * 60:
    # Continue to next gate
```

**Configuration**:

- **Environment**: `VLM_COOLDOWN_MINUTES=1`
- **Config File**: `traffic_analysis.vlm_cooldown_minutes`

#### 5. **Concurrency Gate**: No Pending Analysis

```python
# Prevent duplicate requests for same intersection
if not intersection_state.pending_analysis:
    trigger_vlm_analysis()
```

**Process**:

1. Set `pending_analysis = True`
2. Request fresh camera images via MQTT
3. Initiate async VLM API call
4. Reset `pending_analysis = False` in finally block

### VLM Analysis Workflow

```
Traffic State Change Detected
           ↓
Check All Trigger Conditions
           ↓
Request Fresh Camera Images (MQTT)
           ↓
Acquire VLM Semaphore Slot
           ↓
Collect 4-Direction Camera Images
           ↓
Send to VLM Microservice
           ↓
Store Analysis + Images + Context
           ↓
Release Semaphore Slot
```

## Windowed Analysis System

### Implementation Details

**Purpose**: Solve timing issues where traffic changes before VLM completes, making analysis invisible to users.

#### 1. **Sliding Window Configuration**

```python
# Hardcoded values optimized for traffic scenarios
traffic_window_duration_seconds = 15    # 15-second sliding window
sustained_threshold_seconds = 3         # 3-second sustained requirement  
analysis_display_duration_minutes = 20  # Analysis visibility period
```

#### 2. **Window Management**

```python
@dataclass
class TrafficWindow:
    timestamp: datetime
    directional_densities: Dict[str, float]
    high_density_directions: List[str]

# Per-intersection sliding window
traffic_window: List[TrafficWindow] = []
```

**Process**:

1. Every traffic update adds entry to window
2. Remove entries older than 15 seconds
3. Analyze window for sustained periods ≥ 3 seconds
4. Trigger VLM with traffic context from sustained period

#### 3. **Sustained Traffic Detection**

```python
def _check_sustained_high_traffic(self, state, now):
    # Find periods where high traffic persists ≥ 3 seconds
    # Calculate average and peak densities during period
    # Return traffic context for VLM analysis
```

**Example Timeline**:

```
13:45:00 - Normal traffic (density: 2.1)
13:45:15 - High traffic starts (density: 6.2) → Start sustained period
13:45:18 - Still high (density: 6.5) → Period = 3+ seconds ✅
13:45:20 - VLM triggered with context: "Sustained high eastbound traffic 13:45:15-13:45:20"
13:45:30 - Traffic returns to normal (density: 3.1)
13:45:35 - User checks API → VLM analysis visible with traffic context
```

## Concurrency and Performance

### Multi-Worker VLM Support

**Configuration**:

```python
# VLM microservice worker capacity
VLM_WORKERS = 4  # Default: supports 4 concurrent analyses

# Scene Intelligence semaphore control
vlm_semaphore = asyncio.Semaphore(VLM_WORKERS)
```

### Concurrent Processing Model

```
Scene Intelligence Service           VLM Microservice (4 Workers)
┌─────────────────────────┐         ┌─────────────────────────────┐
│ Intersection-1: High    │────────▶│ Worker-1: Processing        │
│ pending_analysis=True   │         │ Intersection-1 analysis     │
│                         │         │                             │
│ Intersection-2: Normal  │         │ Worker-2: Processing        │
│ No VLM call            │         │ Intersection-3 analysis     │
│                         │         │                             │
│ Intersection-3: High    │────────▶│ Worker-3: Available         │
│ pending_analysis=True   │         │                             │
│                         │         │ Worker-4: Available         │
│ Intersection-4: High    │────────▶│                             │
│ pending_analysis=True   │         │                             │
└─────────────────────────┘         └─────────────────────────────┘
```

**Benefits**:

- Up to 4 intersections analyzed simultaneously
- Each intersection has independent state tracking
- Optimal VLM microservice utilization
- No blocking between intersections

### Timing Example

```
T=00s: Intersection-1 triggers VLM (acquires semaphore slot 1)
T=05s: Intersection-3 triggers VLM (acquires semaphore slot 2)  
T=10s: Intersection-2 triggers VLM (acquires semaphore slot 3)
T=15s: Intersection-4 triggers VLM (acquires semaphore slot 4)
T=20s: Worker-1 completes → Intersection-1 pending_analysis=False
T=25s: Worker-2 completes → Intersection-3 pending_analysis=False
```

## Configuration Parameters

### Environment Variables (Priority: High)

#### Core VLM Service

```bash
# VLM microservice connection
VLM_BASE_URL=http://vlm-openvino-serving:8000          # VLM service endpoint
VLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct                # Model name for analysis

# Concurrency control  
VLM_WORKERS=4                                          # Max concurrent VLM calls
VLM_TIMEOUT_SECONDS=10                                 # VLM API timeout

# Traffic analysis thresholds
HIGH_DENSITY_THRESHOLD=5.0                             # Density threshold for VLM trigger
VLM_COOLDOWN_MINUTES=1                                 # Cooldown between VLM calls per intersection
MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=30  # Persistence requirement

# VLM model parameters
VLM_MAX_COMPLETION_TOKENS=500                          # Max response length
VLM_TEMPERATURE=0.3                                    # Response creativity (0.0-1.0)
VLM_TOP_P=0.9                                         # Response diversity (0.0-1.0)

# Custom prompts (optional)
VLM_SYSTEM_PROMPT="You are an AI traffic analyst..."  # System role prompt
VLM_TRAFFIC_ANALYSIS_PROMPT="Analyze the traffic..."  # Analysis task prompt
```

#### VLM Microservice Configuration

```bash
# Model and device settings
VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct           # Model to load
VLM_DEVICE=CPU                                         # Inference device (CPU/GPU)
VLM_COMPRESSION_WEIGHT_FORMAT=int8                    # Model optimization
VLM_SERVICE_PORT=9764                                  # Service port

# Performance tuning
VLM_WORKERS=4                                          # Uvicorn worker processes
VLM_LOG_LEVEL=info                                     # Logging level
VLM_ACCESS_LOG_FILE=/dev/null                         # Disable access logs

# Optional optimizations
HUGGINGFACE_TOKEN=<token>                             # For private models
OV_CONFIG={"PERFORMANCE_HINT": "LATENCY"}             # OpenVINO optimization
```

### Configuration File (Priority: Medium)

**File**: `config/vlm_config.json`

```json
{
  "vlm_service": {
    "base_url": "${VLM_BASE_URL}",                    // Env var substitution
    "model": "${VLM_MODEL}",
    "timeout_seconds": 10,
    "vlm_workers": 4
  },
  "traffic_analysis": {
    "high_density_threshold": 5.0,
    "minimum_duration_for_consistently_high_traffic_seconds": 30,
    "vlm_cooldown_minutes": 1
  },
  "vlm_model_parameters": {
    "max_completion_tokens": 500,
    "temperature": 0.3,
    "top_p": 0.9
  },
  "prompts": {
    "system_prompt": "You are an AI traffic analyst...",
    "traffic_analysis_prompt": "Analyze the intersection images..."
  }
}
```

**Features**:

- Environment variable substitution using `${VAR_NAME}` syntax
- Fallback values when environment variables not set
- JSON validation on service startup

### Hardcoded Values (Priority: Low)

**Windowed Analysis** (optimized for traffic scenarios):

```python
# File: vlm_service.py
traffic_window_duration_seconds = 15     # Sliding window size
sustained_threshold_seconds = 3          # Minimum sustained duration
analysis_display_duration_minutes = 20   # How long analysis remains visible
```

**Image Request Coordination**:

```python
image_request_cooldown_seconds = 30      # Prevent duplicate image requests
```

**VLM Analysis Retention**:

```python
# clear_old_analyses() method (not called automatically)
max_age_hours = 2                        # Default cleanup threshold
```

## Data Retention and Persistence

### VLM Analysis Results

#### Storage Duration

- **In-Memory**: Stored indefinitely until service restart
- **API Visibility**: 20 minutes after analysis completion
- **Cleanup**: Manual via `clear_old_analyses()` method (2-hour default, never called automatically)

#### Overwrite Behavior

```python
# New analysis overwrites previous for same intersection
self.vlm_results[intersection_id] = new_analysis_result
```

#### Data Structure

```python
@dataclass
class VLMAnalysisResult:
    intersection_id: str
    analysis: str                        # VLM analysis text
    timestamp: datetime                  # When analysis completed
    high_density_directions: List[str]   # Directions that triggered analysis
    confidence: Optional[float]          # VLM confidence score
    
    # Traffic context from windowed analysis
    analysis_period_start: datetime      # When sustained traffic started
    analysis_period_end: datetime        # When sustained traffic ended  
    avg_densities: Dict[str, float]      # Average densities during period
    peak_densities: Dict[str, float]     # Peak densities during period
    
    # Camera images used for analysis
    camera_images: Dict[str, Any]        # Images stored with analysis
```

### Camera Image Retention

#### Storage Logic

1. **VLM Analysis**: Images stored with analysis results
2. **Same Retention**: Images persist as long as VLM analysis exists
3. **API Priority**: Serve VLM-stored images first, then fresh images
4. **Overwrite**: Images replaced when new VLM analysis generated

#### Storage Format

```python
camera_images = {
    "north_camera": {
        "camera_id": "intersection-1_north",
        "direction": "north", 
        "timestamp": "2025-08-20T10:30:00Z",
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
        "image_size_bytes": 45231
    },
    "east_camera": { ... },
    "south_camera": { ... },
    "west_camera": { ... }
}
```

### Traffic State Tracking

#### Per-Intersection State

```python
@dataclass
class IntersectionTrafficState:
    intersection_id: str
    current_state: TrafficState           # NORMAL or HIGH
    state_change_time: datetime           # When state last changed
    last_vlm_analysis: datetime           # When VLM was last triggered
    pending_analysis: bool                # VLM call in progress
    traffic_window: List[TrafficWindow]   # 15-second sliding window
```

#### Persistence

- **Lifetime**: Exists until service restart
- **Reset**: Only when service restarted or intersection removed
- **Updates**: Real-time via MQTT traffic data

## API Integration

### Response Enhancement

All traffic endpoints include VLM analysis when available:

```json
{
  "vlm_analysis": {
    "analysis": "Heavy eastbound congestion due to traffic signal timing...",
    "analysis_timestamp": "2025-08-20T10:30:00Z",
    "analysis_age_minutes": 2.5,
    "high_density_directions": ["eastbound"],
    "current_high_directions": [],        // Current real-time state
    "confidence": 0.85,
    "traffic_context": {
      "analysis_period": {
        "start": "2025-08-20T10:29:15Z",
        "end": "2025-08-20T10:29:45Z", 
        "duration_seconds": 30
      },
      "avg_densities": {
        "northbound": 2.1,
        "southbound": 1.8,
        "eastbound": 5.8,              // High density direction
        "westbound": 1.2
      },
      "peak_densities": {
        "eastbound": 6.2               // Peak during analysis period
      }
    },
    "camera_images": {
      "north_camera": { ... },
      "east_camera": { ... },
      "south_camera": { ... },
      "west_camera": { ... }
    }
  }
}
```

### Image Serving Priority

1. **VLM-Stored Images**: Serve images stored with VLM analysis
2. **Fresh Images**: For high-density intersections without VLM analysis  
3. **No Images**: For normal-density intersections without VLM analysis

## Troubleshooting

### VLM Analysis Not Triggering

Check each gate condition:

```bash
# 1. Traffic density vs threshold
curl http://localhost:8082/api/v1/traffic/directional/summary | jq '.data.intersections[].total_density'
curl http://localhost:8082/api/v1/config/vlm/threshold

# 2. State change detection
docker logs scene-intelligence | grep "Traffic state changed"

# 3. Persistence requirement
echo "Minimum duration: $MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS seconds"

# 4. Cooldown period  
echo "Cooldown: $VLM_COOLDOWN_MINUTES minutes"
docker logs scene-intelligence | grep "cooldown"

# 5. Pending analysis conflicts
docker logs scene-intelligence | grep "pending analysis"
```

### VLM Service Issues

```bash
# Check VLM service health
curl http://localhost:9764/health

# Check semaphore availability
docker logs scene-intelligence | grep "VLM semaphore"

# Check VLM microservice logs
docker logs vlm-openvino-serving

# Verify environment variables
env | grep VLM_
```

### Configuration Validation

```bash
# Check JSON syntax
jq . config/vlm_config.json

# Verify environment variable substitution
docker exec scene-intelligence env | grep VLM_

# Test VLM configuration endpoint
curl http://localhost:8082/api/v1/config/vlm/threshold
```

### Performance Monitoring

```bash
# Monitor VLM call frequency
docker logs scene-intelligence | grep "VLM analysis started"

# Check concurrent analysis count
docker logs scene-intelligence | grep "VLM semaphore acquired"

# Monitor analysis completion times
docker logs scene-intelligence | grep "VLM analysis completed"
```

## Summary

The Scene Intelligence traffic analysis system provides:

- **Real-time directional traffic monitoring** with configurable thresholds
- **AI-powered traffic analysis** using Vision Language Models for high-density situations
- **Windowed analysis** to solve timing issues and provide traffic context
- **Concurrent processing** supporting multiple simultaneous VLM analyses
- **Flexible configuration** via environment variables and config files
- **Image retention** tied to VLM analysis lifecycle
- **Comprehensive API integration** with enhanced traffic context

The system is designed for production environments with proper error handling, logging, and performance optimization while maintaining simple configuration and troubleshooting workflows.
