#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

""" MQTT Client for connecting to broker and publishing messages.
"""

import paho.mqtt.client as mqtt
import logging
import ipaddress, re

class MQTTClient():
    """MQTT Client.
    """

    #MQTTv31 = 3, MQTTv311 = 4, MQTTv5 = 5
    def __init__(self, host, port, topic="dlstreamer_pipeline_results", qos=0, protocol=4, tls_config=None):
        """Constructor
        """
        self.log = logging.getLogger('MQTT_Client')
        self.log.setLevel(logging.INFO)
        self.log.debug(f"In {__name__}...")
        self.host = host
        self.port = port
        self.topics = topic
        self.qos = qos 

        self.invalid_host()
        
        self.client = mqtt.Client(protocol=protocol)
        if tls_config:
            ca_cert = tls_config['ca_cert']
            client_cert = tls_config.get('client_cert', None)
            client_key = tls_config.get('client_key', None)
            self.client.tls_set(ca_cert, client_cert, client_key)
        #Setting max delay to 30s.
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self.on_connect
        self.client.on_log = self.on_log
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        self.client.connect_async(self.host, self.port)
        self.client.loop_start()

    def invalid_host(self):
        try:
            if all(seg.isdigit() for seg in self.host.split('.')) or bool(re.search(r':|::',self.host)):
                ipaddress.ip_address(self.host)
                return
        except:
            raise ValueError("Invalid host ip")

        if not all(bool(re.match("(?!-)[A-Za-z0-9-]{1,63}(?<!-)$", label)) for label in self.host.split('.')):
            raise ValueError("Invalid host name")

    def on_connect(self, client, userdata, flags, rc):
        """ Callback when client receives CONNACK response from the broker/server"""
        if rc == 0:
            self.log.info("Connection to MQTT Broker successful")
        else:
            self.log.error("Connection to MQTT Broker error")

    def on_log(self, client, userdata, level, buf):
        """ Callback for log messages """
        self.log.debug(f"Log: {buf}")

    def on_disconnect(self, client, userdata, rc):
        """ Callback when client disconnects from broker """
        self.log.info("Client disconnected from broker.")

    def on_publish(self, client, userdata, mid):
        """ Callback when message sent from client to broker """
        self.log.debug(f"Message published to MQTT Broker {mid}")
    
    def is_connected(self):
        return self.client.is_connected()

    def publish(self, topic, payload):
        """Publish frame/metadata to MQTT Broker

        :param topic: topic 
        :type: string
        :param payload: payload message
        :type: json
        """
        self.client.publish(topic=topic, payload=payload, qos=self.qos)
    
    def stop(self):
        """Stop MQTT Client
        """
        # for compatibility with other publisher.
        # TODO: Implement safe disconnect. 
        pass
    
