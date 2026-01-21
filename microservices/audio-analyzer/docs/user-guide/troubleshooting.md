# Troubleshooting

This article contains troubleshooting steps for known issues. If you encounter any problems
with the application not addressed here, check the [GitHub Issues](https://github.com/open-edge-platform/edge-ai-libraries/issues)
board. Feel free to file new tickets there.

## Docker Container Fails to Start

    - Run `docker logs {{container-name}}` to identify the issue.
    - Check if the required port is available.

## Cannot Access the Microservice

    - Confirm the container is running:
      ```bash
      docker ps
      ```
