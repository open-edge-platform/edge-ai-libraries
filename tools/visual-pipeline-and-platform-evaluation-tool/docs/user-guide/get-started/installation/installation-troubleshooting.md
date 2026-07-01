# Installation Troubleshooting

This guide provides solutions for common issues encountered during ViPPET installation and deployment.

## Application containers fail to start

In some environments, ViPPET services may fail to start correctly and the UI may not be
reachable. In such cases, stop the currently running containers and start them again with the
default configuration:

- Check container logs:

  ```bash
  docker compose logs
  ```

- Restart the stack using the provided Makefile:

  ```bash
  make stop run
  ```

## Port conflicts for `vippet-ui`

If the `vippet-ui` service cannot be accessed in the browser, it may be caused by a port
conflict on the host. If that is the case, restart the stack and access ViPPET using the new
port, e.g., `http://localhost:8081`:

- In the Compose file (`compose.yml`), find the `vippet-ui` service and its `ports` section:

  ```yaml
  services:
    vippet-ui:
      ports:
        - "80:80"
  ```

- Change the **host port** (left side) to an available one, for example:

  ```yaml
  services:
    vippet-ui:
      ports:
        - "8081:80"
  ```
