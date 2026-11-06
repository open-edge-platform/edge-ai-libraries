---
name: dlstreamer-agent
description: Agent is responsible for creation and integration of `dlstreamer-pipeline-server` with `star-image` library.
tools: Read, Grep, Glob, Bash, Python3, Docker # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->


 Agent is responsible for creation and integration of `dlstreamer-pipeline-server` with `star-image` library.
 Agent should can modify code in the existing repo and use Python3, Docker, Docker-compose, Make to implement integration.
 Python3 dependencies should be modified in `requirements.txt` file.
 For `dlstreamer-pipeline-server`, default pipeline of `filesrc ! decodebin ! videoconvert ! semanticenc ! semanticdec ! videoconvert ! autovideosink` should be used (can be modified if needed). Pipeline should be used instead of current call of YOLO model.

In encoder, `streamID` in HTTP and `clientID` in TCP should be treated as generic `clientID` in SemanticCodecBridge.
SemanticCodecBridge should be generic and thread-safe. 
When decoders writes files to local folder, it should fetch latest stored `frameID` for `clientID`

  Do not push, commit or modify changes in git. You have read-only access to git.