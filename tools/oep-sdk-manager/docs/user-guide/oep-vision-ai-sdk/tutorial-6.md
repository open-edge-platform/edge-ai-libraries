# OEP Vision AI SDK - Tutorial 6

This tutorial walks you through deploying Scenescape using the prebuilt Docker images already downloaded by the OEP Vision AI SDK install script.

## Overview

Scenescape goes beyond single-camera vision AI by fusing data from multiple cameras and sensors into a unified scene graph. It enables spatial awareness, multimodal object tracking, and scene analytics for smart city, retail, and industrial applications.

## Time to Complete

**Estimated Duration:** 10–15 minutes

## Learning Objectives

Upon completion of this tutorial, you will be able to:

- Deploy the Scenescape demo using prebuilt container images
- Access and explore the Scenescape web UI
- Manage Scenescape services with Docker Compose profiles

## Prerequisites

- OEP Vision AI SDK installed (the install script downloads Scenescape images and clones the repo)
- Docker and Docker Compose installed and running

## Tutorial Steps

### Step 1: Navigate to the Scenescape Repository

The OEP Vision AI SDK install script already cloned Scenescape. Navigate to it:

```bash
cd ~/oep/scenescape
```

### Step 2: Initialize Secrets and Models

Generate TLS certificates and download the required OpenVINO models:

```bash
make init-secrets install-models
```

### Step 3: Deploy the Scenescape Demo

Set a super user password and start the demo:

```bash
export SUPASS=<your-password>
make demo
```

> [!NOTE]
> Choose a strong password. This is the admin password for the web UI, not your system password.

### Step 4: Access the Web UI

Open a browser and navigate to:

- **Local:** `https://localhost`
- **Remote:** `https://<ip_address>` or `https://<hostname>`

If you see a certificate warning, this is expected (Scenescape uses a self-signed certificate). Click through to proceed.

Log in with:

- **Username:** `admin`
- **Password:** The value you set for `SUPASS`

The demo includes two pre-configured scenes running from stored video data that you can explore.

To stop the services:

```bash
docker compose --profile controller down --remove-orphans
```

## Next Steps

- [Scenescape Installation](https://docs.openedgeplatform.intel.com/dev/scenescape/get-started/installation.html): Follow the getting started guide to explore core Scenescape functionality
- [How to Use the 3D UI](https://docs.openedgeplatform.intel.com/dev/scenescape/how-to-guides/ui-tutorial.html): Explore the 3D visualization interface
- [How to Integrate Cameras and Sensors](https://docs.openedgeplatform.intel.com/dev/scenescape/how-to-guides/integrate-cameras-and-sensors.html): Connect live cameras and sensors
- [How to Create a New Scene](https://docs.openedgeplatform.intel.com/dev/scenescape/how-to-guides/build-a-scene/create-new-scene.html): Build your own scene from scratch
- [API Reference](https://docs.openedgeplatform.intel.com/dev/scenescape/api-reference.html): Full REST API documentation
