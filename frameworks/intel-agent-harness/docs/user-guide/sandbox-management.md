# Sandbox Management

## Sandbox management (for your own containerized project)

```bash
./install.sh sandbox list
./install.sh sandbox create my-project your-image:tag
./install.sh sandbox stop my-project
./install.sh sandbox backup my-project        # commits a recovery image
./install.sh sandbox recover my-project        # restarts, or rebuilds from backup
./install.sh sandbox destroy my-project --force
./install.sh connect my-project                # open a shell inside it
```

## Sandbox gateway (optional)

By default, sandboxes publish their port straight to the host — simple, but
the container holds its own credentials/env directly and anything on the
host can reach it. Set `HARNESS_GATEWAY_ENABLED=1` to instead route sandbox
traffic through a single shared reverse-proxy container: sandboxes join a
private Docker network with no published port, and the gateway is the only
thing that can reach them.

```bash
export HARNESS_GATEWAY_ENABLED=1
./install.sh sandbox create my-project your-image:tag
./install.sh sandbox list                 # shows the gateway route instead of a host port
```

Routes live in a JSON file under `~/.intel-agent/gateway/`, re-read by the
proxy on every request — no gateway restart needed to add/remove one. A
route can carry a server-held credential (`Authorization` header) that's
injected on the way to the real target; the client's own `Authorization`
header is never forwarded. This is intentionally a single lightweight proxy
container, not a systemd-managed daemon or a full-featured gateway product —
just enough to avoid publishing sandbox ports directly.

Note: this is unrelated to an LLM/MCP routing gateway (e.g. LiteLLM-style
inference gateways) — it only reverse-proxies sandbox container traffic, not
model/agent requests.

## Status

```bash
./install.sh status
```

Read-only combined health view: Docker/GPU, the OpenVINO Model Server, the
installed agent, and every registered sandbox in one place.
