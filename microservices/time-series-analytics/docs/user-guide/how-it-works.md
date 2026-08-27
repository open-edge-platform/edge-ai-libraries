# How It Works

As seen in the following architecture diagram, the `Time Series Analytics` microservice can
take input data from various sources.
The input data that this microservice takes can be broadly divided into two:

- **Input payload and configuration management via REST APIs**
  a. REST clients sending the data in JSON format
  b. Telegraf services sending the data in line protocol format
- **UDF deployment package** (comprises the UDF, TICKScripts, models)
  a. Through Volume mounts OR docker cp OR kubectl cp command

![Time Series Analytics Microservice High Level Architecture](./_assets/Time-Series-Analytics-Microservice-Architecture.png)

As a default flow, we have a sample temperature simulator to ingest data in JSON format and
have pre-packaged simple process based User Defined Function (UDF) in `Time Series Analytics`
microservice to flag the temperature points if they do not fall under a range as anomalies.
The output is seen in the logs of the microservice now.

For understanding the other ways of ingesting data, UDF deployment package configuration,
publishing alerts and writing data back to InfluxDB via TICKScripts, refer to the
following documentation for Time Series sample apps:

- [Overview](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/ai-suite-manufacturing/industrial-edge-insights-time-series/index.html)
- [Get Started](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/ai-suite-manufacturing/industrial-edge-insights-time-series/get-started.html)
- [How to Configure Alerts](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/ai-suite-manufacturing/industrial-edge-insights-time-series/how-to-guides/configure-alerts.html)
- [Deploy with Custom UDF](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/ai-suite-manufacturing/industrial-edge-insights-time-series/how-to-guides/configure-custom-udf.html)

## Summary

This guide provides an overview of the architecture of the Time Series Analytics Microservice.
For more details, refer to [Get Started](./get-started.md).
