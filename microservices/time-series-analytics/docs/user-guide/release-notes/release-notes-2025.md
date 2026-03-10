# Release Notes: Time Series Analytics 2025

## Version 2025.2

**December 10, 2026**

This release introduces comprehensive configuration improvements, GPU acceleration support,
and enhanced security measures for the microservice. It offers two deployment options:

- Docker compose deployment on single node
- Helm deployment on kubernetes single cluster node

**New**

- **GPU Acceleration**: Added GPU device support with Intel oneAPI integration for improved inference performance
- **Enhanced Documentation**: New comprehensive configuration guides for UDFs, MQTT alerts, and OPC UA alerts
- Device selection support for CPU or GPU inference

**Improved**

- **Docker Optimization**: Upgraded to Kapacitor 1.8.2 with multistage builds for improved efficiency and security
- New "How to Configure" guide with example JSON configurations
- DockerHub documentation for Docker images and Helm charts
- Upgraded base Docker image from Kapacitor 1.7.7 to 1.8.2
- Enabled multistage Docker builds reducing image size
- Added Nginx root URL routing support
- Updated Helm charts and deployment configurations
- Improved HTTP status code handling (400, 422, 503) for better error reporting
- Standardized logging format using parameterized strings
- Removed deprecated Model Registry references
- Cleaned up documentation structure across components
- Removed oneAPI toolkit to reduce image size

**Fixed**
- Fixed Trivy security vulnerabilities by updating FastAPI and Kubernetes configurations
- Resolved bandit security vulnerability for tmp directory usage
- Fixed Python linting issues with comprehensive docstrings
- Fixed OPC UA alert error code propagation
- Corrected documentation links and architecture references
- Updated OPC UA server certificate naming
- Fixed variable naming and removed duplicate imports

**Upgrade Notes**

- Docker images now use Kapacitor 1.8.2 - UDF implementations updated for API compatibility
- Helm chart version updated from 1.0.0 to 1.1.0-weekly
- Python dependencies updated across multiple licenses

More details at [user-guide](../../user-guide/index.md)

## Version v1.0.0

**August, 2026**

This is the first version of the `Time Series Analytics` microservice.
It offers two deployment options:

- Docker compose deployment on single node
- Helm deployment on kubernetes single cluster node

**New**

- **Bring your own Data Sets and corresponding User Defined Functions(UDFs) for custom analytics**: Easily implement and deploy your own Python-based analytics logic, following Kapacitor’s UDF standards.
- **Seamless Integration**: Automatically stores processed results back into InfluxDB for unified data management and visualization.
- **Model Registry Support**: Dynamically fetch and deploy UDF scripts, machine learning models, and TICKscripts from the Model Registry microservice, enabling rapid customization and iteration.
- **Versatile Use Cases**: Ideal for anomaly detection, alerting, and advanced time series analytics in industrial, IoT, and enterprise environments.

More details at [user-guide](../../user-guide/index.md)