#!/usr/bin/env python3
import sys
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import json
import base64
import cv2
import numpy as np
import re

class SimpleSubscriber(Node):
    def __init__(self, topic_name):
        super().__init__('simple_subscriber')
        self.topic_name = topic_name
        self.subscription = self.create_subscription(
            String,
            topic_name,
            self.listener_callback,
            10
        )
        self.counter = 0
        # clean topic name for filename (remove /)
        self.topic_safe = re.sub(r'[^a-zA-Z0-9_]', '_', topic_name)
        print(f"Subscribed to topic: {topic_name}")

    def listener_callback(self, msg):
        try:
            data = json.loads(msg.data)

            metadata = data.get("metadata", {})
            print(f"Metadata on topic {self.topic_name}: {metadata}")

            image_b64 = data.get("blob", "")
            if image_b64:
                img_bytes = base64.b64decode(image_b64)
                np_arr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                
                if img is not None:
                    filename = f"{self.topic_safe}_{self.counter}.jpg"
                    cv2.imwrite(filename, img)
                    print(f"Image from topic {self.topic_name} saved to {filename}")
                    self.counter += 1
                else:
                    print("Failed to decode image.")
            else:
                print("No image data in message.")

        except Exception as e:
            print(f"Error on topic {self.topic_name}: {e}")

def main(args=None):
    rclpy.init(args=args)

    # get topic from command line
    topic_name = '/dlstreamer_pipeline_result'  # default
    if len(sys.argv) > 1:
        topic_name = sys.argv[1]

    node = SimpleSubscriber(topic_name)
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
