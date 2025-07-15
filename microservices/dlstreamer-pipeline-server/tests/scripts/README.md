# Automation Framework for DLStreamer Pipeline Server

This directory contains sanity test scripts and utility functions required for automation testing.

### Installation Steps:

1. **Update the system and install required packages:**

    ```sh
    sudo apt-get update
    sudo pip3 install robotframework
    sudo apt install python3-nose
    ```

## Automation Tests Folder Structure

The folder structure is designed to ensure a clear and organized workflow.

### Folder Structure:

1. **configs:** Contains files required to configure the environment.
2. **common_library:** Contains utility scripts.
3. **functional_tests:** Contains Python test files.
4. **robot_files:** Contains Robot Framework test files.
5. **utils:** Contains scripts to manage RTSP servers.

```
tests --> scripts 
            |--> configs 
            |--> common_library
            |--> functional_tests
            |--> robot_files
            |--> utils
```

## Managing RTSP Servers

### Starting RTSP Servers:

To start RTSP servers in the background, execute the following commands:

```sh
cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/tests/scripts/utils/
chmod a+x stream_rtsp.sh
./stream_rtsp.sh start <no_of_streams> <path_to_video> <system_ip>
```

- Replace `<no_of_streams>` with the number of streams to start.
- Replace `<path_to_video>` with the path to the video file.
- Replace `<system_ip>` with the system's IP address.

### Stopping RTSP Servers:

To stop the RTSP servers, run:

```sh
./stream_rtsp.sh stop
```

## Running DLStreamer Pipeline Server Automation Tests

To run sanity test cases for DLStreamer Pipeline Server, use the following command:

```sh
cd edge-ai-libraries/microservices/dlstreamer-pipeline-server/tests/scripts/robot_files
robot test_main_sanity.robot
```

- **Explanation:**
  - `robot test_main_sanity.robot` executes the Robot Framework sanity test file.

After running the tests, the following files will be generated in the `robot_files` directory:
- `log.html`
- `output.xml`
- `report.html`

To view the test results, open the `report.html` file in a web browser.