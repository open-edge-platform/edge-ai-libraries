# Deploy with Helm Chart

The chart is located in `microservices/sensor-manager/chart`.

## Install

```bash
cd edge-ai-libraries/microservices/sensor-manager
helm install sensor-manager ./chart \
  --set image.registry=<registry>/ \
  --set image.tag=<tag>
```

## Key Values

| Value | Default | Description |
|-------|---------|-------------|
| `hostNetwork` | `true` | Required for ONVIF WS-Discovery. The service listens on the node's interfaces on `port`. |
| `port` | `8090` | HTTP port of the service |
| `env.ONVIF_DISCOVERY_ENABLED` | `"true"` | Enable ONVIF discovery |
| `env.ONVIF_DISCOVERY_INTERVAL_S` | `"20"` | Seconds between discovery sweeps |
| `usb.enabled` | `false` | Mount the node's `/dev` for USB cameras |
| `usb.videoGroupId` | `44` | GID of the node's `video` group |
| `service.type` / `service.port` | `ClusterIP` / `8090` | Kubernetes Service |

## Security Considerations

- With `hostNetwork: true` the API is exposed on the node network without authentication.
  Restrict access with NetworkPolicies or node firewall rules.
- `usb.enabled: true` runs the container as privileged, because Kubernetes cannot grant access
  to individual device classes the way Docker's `device_cgroup_rules` does. Enable it only on
  trusted, dedicated nodes, and pin the pod to them with `nodeSelector`.
- The pod runs as UID/GID 1000 with a read-only root filesystem, all capabilities dropped and
  the `RuntimeDefault` seccomp profile.

## Uninstall

```bash
helm uninstall sensor-manager
```
