# Pinning the DL Streamer Pipeline Sever to CPU cores

The DL Streamer Pipeline Server supports `CORE_PINNING` if you need to pin the server to certain CPU cores for performance optimization. The `CORE_PINNING` environment variable takes the following values:
- A comma delimited list of CPU cores or range of CPU cores: `10,12,14` or `10-14` or `10-14/2`. See the `taskset` documentation for more details of how to specify the list of CPU cores.
- A specific core type such as `e-cores`, `p-cores`, or `lp-cores`.

The following is an example of how to specify CPU cores in a docker-compose file:

```text
...
  services:
    dlstreamer-pipeline-server:
    image: intel/dlstreamer-pipeline-server:3.1.0-ubuntu22
    environment:
      CORE_PINNING: p-cores
...
```

