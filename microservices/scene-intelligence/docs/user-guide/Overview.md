# Scene Intelligence microservice

The Scene Intelligence microservice is a comprehensive traffic analysis service that provides real-time intersection monitoring, directional traffic density analysis, and Vision Language Model (VLM) powered traffic insights. It processes MQTT traffic data, manages camera images, and delivers intelligent traffic analysis through RESTful APIs.

## Overview

The microservice processes real-time traffic data from MQTT streams and provides advanced analytics including directional traffic density monitoring, VLM-powered traffic scene analysis, and comprehensive traffic summaries. It supports sliding window analysis, sustained traffic detection, and intelligent camera image management for enhanced traffic insights.

## Features supported

| Feature                             | Real-time Processing | Historical Analysis | VLM Integration | Camera Integration      |
|-------------------------------------|----------------------|---------------------|-----------------|-------------------------|
| Directional Traffic Density        | ✅ Yes               | ❌ No               | ✅ Yes          | ✅ Yes                  |
| Intersection Monitoring             | ✅ Yes               | ❌ No               | ✅ Yes          | ✅ Yes                  |
| MQTT Data Processing                | ✅ Yes               | ❌ No               | ❌ No           | ✅ Yes                  |
| Sliding Window Analysis             | ✅ Yes               | ❌ No               | ✅ Yes          | ❌ No                   |
| VLM Traffic Scene Analysis          | ✅ Yes               | ❌ No               | ✅ Yes          | ✅ Yes                  |
| Camera Image Management             | ✅ Yes               | ⚠️ Limited*         | ✅ Yes          | ✅ Yes                  |
| Configuration Management            | ✅ Yes               | ❌ No               | ✅ Yes          | ❌ No                   |
| Debug and Diagnostics               | ✅ Yes               | ❌ No               | ✅ Yes          | ✅ Yes                  |

**Notes:**

- *Limited*: Camera images are retained only as long as VLM analysis is stored (20 minutes display + indefinite storage until restart)
- **Historical Analysis**: Service processes real-time data only; no time-based queries or historical data storage
- **VLM Integration**: Advanced AI analysis for high-density traffic situations with configurable triggers and windowed analysis

## Supporting Resources

- [Get Started Guide](get-started.md)
- [Traffic Data Analysis Workflow](traffic-data-analysis-workflow.md) - **Comprehensive guide to traffic analysis, VLM integration, and configuration**
- [API Reference](api-reference.md)
- [System Requirements](system-requirements.md)
