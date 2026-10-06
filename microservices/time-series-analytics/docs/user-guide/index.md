# Time Series Analytics

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/time-series-analytics">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/time-series-analytics/README.md">
     Readme
  </a>
</div>
hide_directive-->

The Time Series Analytics microservice provides the analytics capabilities for a time series
use case.

It provides a FastAPI control and ingestion API for **InfluxDB 3 Core**. Core stores the time
series and runs Python Processing Engine plugins through table or scheduled triggers.

What sets this microservice apart is its support for advanced analytics through
**User-Defined Functions (UDFs)** written in Python. By leveraging the Intel® Extension for
**Scikit-learn**, you can accelerate machine learning workloads within their UDFs, unlocking
high-performance anomaly detection, predictive maintenance, and other sophisticated analytics.

The key features include:

- **Bring your own Data Sets and corresponding User Defined Functions (UDFs) for custom analytics**:
Easily implement and deploy Python Core Processing Engine plugins with optional models and dependencies.
- **Seamless Integration**: Automatically stores processed results back into InfluxDB for
unified data management and visualization.
- **Versatile Use Cases**: Ideal for anomaly detection, alerting, and advanced time series
analytics in industrial, IoT, and enterprise environments.

For the Wind Turbine plugin and end-to-end deployment, see the
[Industrial Edge Insights Time Series suite](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/industrial-edge-insights-time-series).

<!--hide_directive
:::{toctree}
:hidden:

get-started
how-it-works
how-to-access-api
how-to-configure
api-reference
Release Notes <release-notes.md>

:::

hide_directive-->
