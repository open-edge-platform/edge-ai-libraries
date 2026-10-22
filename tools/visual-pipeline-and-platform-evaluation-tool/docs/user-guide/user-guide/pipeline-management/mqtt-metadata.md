# Publishing Metadata Over MQTT

Inference metadata produced by a pipeline is normally written to a file and shown in the **Metadata JSON** panel.
The `gvametapublish` element can instead publish each frame's metadata to an MQTT broker, so that another
application can consume detections, classifications, and tensor data while the pipeline runs.

This page explains how to start a broker, point a pipeline at it, and subscribe to the published messages.

## Starting a Broker

ViPPET ships an optional Mosquitto broker in `compose.mqtt.yml`. The service is named `mqtt-broker` and listens
on port `1883`. There are two ways to start it.

### Option 1: Start the Broker With the Stack

Pass `MQTT=1` to `make run`:

```bash
make run MQTT=1
```

This starts the whole stack plus the broker. `make run-dev MQTT=1` works the same way for the development setup.

### Option 2: Add the Broker to a Running Stack

If the stack is already running without the broker, start just that service. It joins the existing Compose
network, so no restart of the other services is needed:

```bash
. .env && docker compose -f compose.yml -f compose.$COMPOSE_PROFILES.yml \
  -f compose.mqtt.yml up -d mqtt-broker
```

Either way, `make stop` removes the broker along with the rest of the stack.

### Using Your Own Broker

An external broker works too. It only has to be reachable from the `vippet` container:

- A broker on your host machine is reachable as `host.docker.internal:1883`.
- A broker in another container must be attached to the same Docker network, otherwise its name does not resolve.
- `localhost` always refers to the `vippet` container itself and never reaches a broker outside it.

## Configuring a Pipeline

MQTT settings live on the `gvametapublish` element, which is only visible in the advanced view.

1. Open a pipeline and switch to the advanced view.
2. Select the **GVAMetaPublish** node to open the node panel.
3. Set **Method** to `mqtt`. The file options are replaced by the broker options.
4. Check **Broker Address** and **Topic**, then run the pipeline.

The defaults match the bundled broker, so no changes are needed when the pipeline runs with `MQTT=1`.

| Field                  | Default            | Description                                                                        |
|------------------------|--------------------|------------------------------------------------------------------------------------|
| Method                 | `file`             | Publish to a file or to an MQTT broker.                                            |
| Broker Address         | `mqtt-broker:1883` | Host and port, resolved from inside the `vippet` container.                        |
| Topic                  | `vippet/metadata`  | Topic the metadata is published on.                                                |
| Client ID              | *(empty)*          | Client identifier. One is generated when left empty.                               |
| Max Connect Attempts   | `1`                | Failed connection attempts before the pipeline fails. Range 1-10.                  |
| Max Reconnect Interval | `30`               | Upper bound in seconds between reconnect attempts. Range 1-300.                    |
| Config File            | *(empty)*          | Path to a JSON file with credentials and TLS settings. Overrides the fields above. |

Behind an HTTP proxy, no extra configuration is needed. The MQTT client library ignores `no_proxy` and would
otherwise route broker traffic through the proxy, so ViPPET removes the proxy variables from the GStreamer
process whenever a pipeline publishes to a broker.

## Subscribing to the Output

Any MQTT client can subscribe. The examples below use `mosquitto_sub` with the topic wildcard `#`.

From the broker container, which needs no extra tooling on your machine:

```bash
docker exec mqtt-broker mosquitto_sub -h localhost -t '#' -v
```

From your host machine, using the published port:

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'vippet/metadata' -v
```

From another container on the same network:

```bash
docker run --rm --network visual-pipeline-and-platform-evaluation-tool_default \
  eclipse-mosquitto:2.0.22 mosquitto_sub -h mqtt-broker -t '#' -v
```

Each message is one JSON object per frame, in the same format the metadata file uses:

```json
{
  "objects": [
    {
      "detection": {
        "bounding_box": {"x_max": 0.60, "x_min": 0.39, "y_max": 0.62, "y_min": 0.11},
        "confidence": 1.0,
        "label": "face",
        "label_id": 1
      },
      "id": 1,
      "roi_type": "face"
    }
  ],
  "resolution": {"height": 2160, "width": 3840},
  "timestamp": 0
}
```

To include raw inference tensors, such as re-identification embeddings, enable **Add Tensor Data** on the
`gvametaconvert` node. Tensor data makes messages considerably larger.

## Relationship to the Metadata JSON Panel

The **Metadata JSON** panel reads the file written by a `gvametapublish` element using `method=file`. A single
element publishes to one destination, so switching it to `mqtt` means the panel no longer has a file to read and
the option disappears for that pipeline.

To keep both, add a second branch with a `tee` so that one `gvametapublish` writes a file and another publishes
to the broker.

## Security Considerations

The bundled broker is intended for local evaluation. It accepts unauthenticated clients, so `compose.mqtt.yml`
publishes port `1883` on the loopback interface only. Override `MQTT_BROKER_PUBLISH` to expose it elsewhere, and
only do so on a trusted network:

```bash
MQTT_BROKER_PUBLISH=0.0.0.0:1883 make run MQTT=1
```

Credentials and TLS settings belong in a JSON file referenced by **Config File**, not in the node fields. A
pipeline description is stored in the database and appears in logs, so a password typed into the pipeline would
be exposed. The file accepts `username`, `password`, `TLS`, and the `ssl_*` certificate paths. See the
[gvametapublish documentation][gvametapublish] for the full schema.

## Troubleshooting

**The pipeline fails with "Failed to connect to MQTT after maximum configured attempts".**
The broker is not reachable at the configured address. Confirm the broker is running, and that the address is
resolvable from the `vippet` container rather than from your host:

```bash
docker exec vippet getent hosts mqtt-broker
```

Remember that `localhost` points at the `vippet` container. Use the service name or `host.docker.internal`.

**The pipeline runs but no messages arrive.** Check that the subscriber uses the same topic as the pipeline, or
subscribe to `#` to see every topic.

**No broker is running.** The pipeline fails quickly with a connection error rather than discarding the data
silently. Raising **Max Connect Attempts** only delays the failure, because the retry backoff blocks the
pipeline while it waits.

[gvametapublish]: https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/elements/gvametapublish.html
