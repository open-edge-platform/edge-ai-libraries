# System Requirements

- Linux host (Ubuntu 22.04 or 24.04 recommended) with Docker Engine 24+ and Docker Compose v2.
- For USB cameras: V4L2-compatible cameras visible as `/dev/video*`.
- For ONVIF cameras: cameras on the same layer-2 network segment as the host, with UDP
  multicast (`239.255.255.250:3702`) allowed by the network and the host firewall.
- For development: Python 3.12 and [uv](https://docs.astral.sh/uv/).
- Network access to `github.com` when building the image. The `dlstreamer.onvif` library is
  installed from a pinned commit of the DL Streamer repository.
