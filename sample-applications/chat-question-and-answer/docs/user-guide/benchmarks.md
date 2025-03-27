# Benchmarks

This document provides reference benchmark results for the ChatQ&A sample application. The benchmark numbers published here are indicative of the performance to be expected on given test environment. 

## Test Environment

- **Processor:** Intel Xeon 4th generation
- **Memory:** 1TB DDR4
- **Storage:** 8TB NVMe SSD
- **Operating System:** Ubuntu 22.04.2 LTS

## Benchmark Results
The benchmark was done at a microservice level and for end-to-end application. Numbers under each bucket is provided below.

### LLM served with OVMS 

| Metric       | Average  | Min |  Max |
|-----------------|-----------------------------|-------------------------|--------------------------|
| TTFT (ms)    | 1202.07  |1148.71  | 1306.06 |
| Output toekn throughput (per sec)   | 23.22  | NA  | NA |     
| Request latency (ms)| 11427.07 | 11383.02  | 11499.36  |

### TBD: Check if such information can be published?

