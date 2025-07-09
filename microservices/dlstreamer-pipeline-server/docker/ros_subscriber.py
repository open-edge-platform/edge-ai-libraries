#!/usr/bin/env python3
import sys
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

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
        print(f"Subscribed to topic: {topic_name}")

    def listener_callback(self, msg):
        print(f"On topic {self.topic_name}, received message: {msg.data}")

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
