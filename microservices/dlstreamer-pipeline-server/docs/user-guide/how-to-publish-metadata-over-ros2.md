# How to publish metadata over ROS2

DL Streamer Pipeline Server offers publishing the metadata (with or without encoded frames) over ROS2.

## Prerequisite

Ensure to build/pull the DL Streamer Pipeline Server extended image i.e., `intel/dlstreamer-pipeline-server:<version>-extended-ubuntu<ubuntu-version>`.

[Build instructions](./how-to-build-from-source.md)

[Pull image](https://hub.docker.com/r/intel/dlstreamer-pipeline-server)

## Publish 

- A sample config has been provided for this demonstration at `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_ros2_publisher/config.json`. We need to volume mount the sample config file into dlstreamer-pipeline-server service present in `[WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/docker/docker-compose.yml` file. Refer below snippets:

    ```sh
        volumes:
        # Volume mount [WORKDIR]/edge-ai-libraries/microservices/dlstreamer-pipeline-server/configs/sample_ros2_publisher/config.json to config file that DL Streamer Pipeline Server container loads.
        - "../configs/sample_ros2_publisher/config.json:/home/pipeline-server/config.json"
    ```

- Start the services
    ```sh
        docker compose up
    ```
- Open another terminal and start a pipeline in DL Streamer Pipeline Server with the below curl command. This would publish the pipeline output metadata over ROS2.
    ```sh
        curl localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection -X POST -H 'Content-Type: application/json' -d '{
            "source": {
                "uri": "file:///home/pipeline-server/resources/videos/warehouse.avi",
                "type": "uri"
            },
            "destination": {
                "metadata": {
                    "type": "ros2",
                    "publish_frame": false,
                    "topic": "/dlstreamer_pipeline_results"
                }
            },
            "parameters": {
                "detection-properties": {
                    "model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml",
                    "device": "CPU"
                }
            }
        }'
    ```
    Note: In the above command, do `"publish_frame": true` to send encoded frame as a part of metadata over ROS2.


## Subscribe (Example)

Below is an example that shows how to subscribe to the published data.

- Install ROS2 Humble on Ubuntu22 and source it. Install python and related dependencies too.
    ```sh
        # Install ROS2 Humble
        sudo apt update && sudo apt install -y curl gnupg lsb-release
        sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
            http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | \
            sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
        sudo apt update
        sudo apt install -y ros-humble-ros-base python3-colcon-common-extensions

        # Source ROS2 Humble
        source /opt/ros/humble/setup.bash

        # Install Python and dependencies
        sudo apt install -y python3 python3-pip python3-opencv
    ```

- Install ROS2 Jazzy on Ubuntu24 and source it. Install pythyon and related dependencies too.
    ```sh
        # Install ROS2 Jazzy
        sudo apt update && sudo apt install -y curl gnupg lsb-release
        sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
            http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | \
            sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
        sudo apt update
        sudo apt install -y ros-jazzy-ros-base python3-colcon-common-extensions

        # Source ROS2 Jazzy
        source /opt/ros/jazzy/setup.bash

        # Install Python and dependencies
        sudo apt install -y python3 python3-pip python3-opencv
    ```

- Save the below sample subscriber script as `ros_subscriber.py`
    ```python
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
        topic_name = '/dlstreamer_pipeline_results'  # default
        if len(sys.argv) > 1:
            topic_name = sys.argv[1]

        node = SimpleSubscriber(topic_name)
        rclpy.spin(node)
        node.destroy_node()
        rclpy.shutdown()

    if __name__ == '__main__':
        main()
    ```

- Run the sample subscriber script as follows and view the metadata being printed and frames being saved.
    ```sh
    python3 ros_subscriber.py /dlstreamer_pipeline_results
    ```