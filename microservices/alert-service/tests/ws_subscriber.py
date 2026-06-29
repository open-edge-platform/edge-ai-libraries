"""Subscribe to MQTT alerts over WebSocket (port 9001)."""

import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected (rc={rc})")
    client.subscribe("alerts/#")


def on_message(client, userdata, msg):
    print(f"[{msg.topic}] {msg.payload.decode()}")


client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    transport="websockets",
)
client.connect("localhost", 9001)
client.on_connect = on_connect
client.on_message = on_message
client.loop_forever()
