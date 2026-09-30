# Installation Troubleshooting

This guide provides solutions for common issues encountered during ViPPET installation and deployment.

## `no such file or directory` for `/dev/dri`

If starting the stack fails with:

```text
Error response from daemon: error gathering device information while adding custom device "/dev/dri": no such file or directory
```

while `ls /dev/dri` on the host lists a render node such as `renderD128`, the Docker daemon is not running on the
host kernel. This is the case with **Docker Desktop on Linux**, which runs the daemon inside a virtual machine that
has no access to the host render nodes, so the device cannot be passed into the containers.

- Confirm which daemon is in use:

  ```bash
  docker context ls
  docker run --rm --device /dev/dri:/dev/dri alpine ls -l /dev/dri
  ```

  With Docker Engine, the active context endpoint is `unix:///var/run/docker.sock` and the test container lists the
  render node.

- To resolve it, [uninstall Docker Desktop](https://docs.docker.com/desktop/uninstall/), then install
  [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) and complete the
  [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/). A reboot may be required for
  the new group membership to take effect.

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
