# Stream Manager

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/stream-manager">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/stream-manager/README.md">
     Readme
  </a>
</div>
hide_directive-->

Stream Manager attaches to RTSP video sources, records selected intervals, and serves frames and
clips by timestamp.

Live recording uses filesystem storage and SQLite metadata. S3-compatible storage supports
retrieval of archived recordings published by an external producer.

## Overview

Use the setup guide to attach a camera and record video. Use the API reference to call stream,
recording, and replay endpoints.

- [Get Started](get-started.md)
- [API Reference](api-reference.md)

<!--hide_directive
:::{toctree}
:hidden:

get-started
api-reference

:::
hide_directive-->
