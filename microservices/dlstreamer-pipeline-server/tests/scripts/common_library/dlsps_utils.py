#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os, sys, time, json, yaml, subprocess, os.path, requests
from collections import OrderedDict

current_dir = os.path.abspath(os.path.dirname(__file__))
repo_path = os.path.abspath(os.path.join(os.getcwd(), "../../../"))

sys.path.extend([
    os.path.abspath(current_dir),
    os.path.abspath(os.path.join(current_dir, '../configs'))
])

hostIP = subprocess.check_output("ip route get 1 | awk '{print $7}'|head -1", shell=True).decode('utf-8').strip()

base_source_uri = {"uri": "file:///home/pipeline-server/resources/videos/warehouse.avi", "type": "uri"}
base_detection_properties = {"model": "/home/pipeline-server/resources/models/geti/pallet_defect_detection/deployment/Detection/model/model.xml", "device": "CPU"}
base_rtsp_frame = {"type": "rtsp", "path": "pallet_defect_detection"}

def create_pipeline_config(source, destination_frame, detection_properties):
    return {
        "source": source,
        "destination": {"frame": destination_frame},
        "parameters": {"detection-properties": detection_properties}}

pipeline_sources = {
    "rtsp": {"uri": f"rtsp://{hostIP}:8555/live.sdp", "type": "uri"},
    "file": base_source_uri
}

dlsps_data = {
    "gvadetect_rtsp": create_pipeline_config(
        source=pipeline_sources["rtsp"],
        destination_frame=base_rtsp_frame,
        detection_properties=base_detection_properties
    ),
    "gvadetect": create_pipeline_config(
        source=pipeline_sources["file"],
        destination_frame=base_rtsp_frame,
        detection_properties=base_detection_properties
    )
}

dlsps_data_gvadetect_rtsp = dlsps_data["gvadetect_rtsp"]
dlsps_data_gvadetect = dlsps_data["gvadetect"]

class dlsps_utils():
    """
    Utility class for managing and testing the DL Streamer Pipeline Server.

    Attributes:
        repo_path (str): Path to the repository root.
        dlsps_path (str): Path to the Docker directory for DL Streamer Pipeline Server.
        dlsps_config (str): Path to the default configuration file.
    """

    def __init__(self):
        """
        Initializes the dlsps_utils class with repository paths.
        """
        self.repo_path = repo_path
        self.dlsps_path = f"{repo_path}/docker"
        self.dlsps_config = f"{repo_path}/configs/default/config.json"
        print(f"dlsps_path: {self.dlsps_path}")
        print(f"dlsps_config: {self.dlsps_config}")


    def json_reader(self, tc, JSON_PATH):
        """
        Reads a JSON file and retrieves the value for a specific test case.

        Args:
            tc (str): Test case key to search for in the JSON file.
            JSON_PATH (str): Path to the JSON file.

        Returns:
            The test case key and its value.
        """
        print('\n********** Reading json **********')
        with open(JSON_PATH, "r") as jsonFile:
            json_config = json.load(jsonFile)
        for key, value in json_config.items():
            if key == tc:
                print("**********Test Case : ", key, "**********","\n**********Value : ", value, "**********")
                return key, value


    def change_docker_compose_for_standalone(self):
        """
        Updates the Docker Compose configuration for standalone mode.

        Modifies the `.env` file to set the RTSP_CAMERA_IP and updates the
        `docker-compose.yml` file to include the default configuration volume.
        """
        print('\n********** Updating docker-compose.yml **********')
        os.chdir(self.dlsps_path)
        for key, value in {'RTSP_CAMERA_IP': hostIP}.items():
            subprocess.run("sed -i 's#{Key}=.*#{Key}={Value}#g' .env".format(Key=key, Value=value), shell=True, executable='/bin/bash', check=True)
        with open("docker-compose.yml", 'r') as file:
            data = yaml.safe_load(file)
        service = data.get('services', {}).get('dlstreamer-pipeline-server', {})
        volumes = service.get('volumes', [])
        config_path = "../configs/default/config.json"
        volumes.append(f"{os.path.abspath(config_path)}:/home/pipeline-server/config.json")
        service['volumes'] = volumes
        with open("docker-compose.yml", 'w') as file:
            yaml.safe_dump(data, file)


    def common_service_steps_dlsps(self):
        """
        Builds and runs the DL Streamer Pipeline Server using Docker Compose.
        """
        print('********** Building and running dlsps **********')
        os.chdir(self.dlsps_path)
        subprocess.run('docker compose build', shell=True, executable='/bin/bash', check=True)
        subprocess.run('docker compose up -d', shell=True, executable='/bin/bash', check=True)


    def change_config_for_dlsps_standalone(self, value):
        """
        Updates the DL Streamer Pipeline Server configuration file.

        Args:
            value (dict): Dictionary containing the new source configuration and pipeline type.
        """
        print('********** Changing config.json **********')
        with open(self.dlsps_config, "r") as jsonFile:
            data = json.load(jsonFile, object_pairs_hook=OrderedDict)
            config_path = "config"
            if config_path in data:
                pipeline_config = data[config_path]["pipelines"][0]
                pipeline_config["source"] = value["source_conifg"]
                if value.get("type_r")=="autosource":
                    pipeline_config["pipeline"] = "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! gvametapublish name=destination ! appsink name=appsink"
                elif value.get("type_r")=="autosource_destination":
                    pipeline_config["pipeline"] = "{auto_source} name=source  ! decodebin ! videoconvert ! gvadetect name=detection model-instance-id=inst0 ! queue ! gvawatermark ! gvafpscounter ! gvametaconvert add-empty-results=true name=metaconvert ! appsink name=destination"            
            with open(self.dlsps_config, "w") as jsonFile:
                json.dump(data, jsonFile, indent=4)


    def execute_curl_command(self, value):
        """
        Sends a POST request to start a pipeline and checks its status.

        Args:
            value (dict): Dictionary containing the instance type and other parameters.

        Raises:
            Exception: If the pipeline is in an unexpected state or not found.
        """
        instance_map = {
            "auto_source_gvadetect": dlsps_data_gvadetect,
            "auto_source_gvadetect_rtsp": dlsps_data_gvadetect_rtsp,
        }
        data = instance_map.get(value.get("instance"), dlsps_data_gvadetect)
        url = "http://localhost:8080/pipelines/user_defined_pipelines/pallet_defect_detection"
        dlsps_headers = {'Content-Type': 'application/json'}
        print(f"Sending POST request to {url} with data: {json.dumps(data, indent=4)}")
        time.sleep(3)
        response = requests.post(url, headers=dlsps_headers, data=json.dumps(data))
        response.raise_for_status()
        pipeline_id = response.text[1:33]
        print(f"Pipeline started with ID: {pipeline_id}")
        status_url = "http://localhost:8080/pipelines/status"
        time.sleep(3)
        status_response = requests.get(status_url)
        status_response.raise_for_status()
        status_data = status_response.json()
        for status in status_data:
            if status.get("id") == pipeline_id:
                pipeline_state = status.get("state")
                print(f"Pipeline {pipeline_id} state: {pipeline_state}")
                if pipeline_state in ["RUNNING", "COMPLETED"]:
                    print("Pipeline is running or completed successfully.")
                    return
                else:
                    raise Exception(f"Pipeline {pipeline_id} is in unexpected state: {pipeline_state}")
            else:
                raise Exception(f"Pipeline {pipeline_id} not found in status response.")


    def container_logs_checker_dlsps(self, tc, value):
        """
        Checks the logs of specified Docker containers for specific keywords.

        Args:
            tc (str): Test case identifier.
            value (dict): Dictionary containing container names and keywords to check.

        Returns:
            bool: True if all keywords are found in the logs, False otherwise.
        """
        print('********** Checking container logs **********')
        time.sleep(3)
        containers = value.get("check_logs", "").split()
        log_present = {}
        for container in containers:
            log_file = f"logs_{container}_{tc}.txt"
            print(f"================== {container} ==================")
            subprocess.run(f"docker compose logs --tail=1000 {container} | tee {log_file}", shell=True, executable='/bin/bash', check=True)
            keywords = value.get({'dlstreamer-pipeline-server': "dlsps_log_param"}.get(container, ""), [])
            log_present[container] = all(self.search_element(log_file, keyword) for keyword in keywords)
            if not log_present[container]:
                print(f"FAIL: Keywords not found in logs for container {container}")
                return False
        if log_present.get("dlstreamer-pipeline-server"):
            print("PASS: All keywords found in logs.")
            return True
        print("FAIL: Keywords not found in logs.")
        return False


    def search_element(self, logFile, keyword):
        """
        Searches for a specific keyword in a log file.

        Args:
            logFile (str): Path to the log file.
            keyword (str): Keyword to search for.

        Returns:
            bool: True if the keyword is found, False otherwise.
        """
        keyword_found = False
        keywords_file = os.path.abspath(logFile)
        with open(keywords_file, 'rb') as file:
            for curr_line in file:
                each_line = curr_line.decode()
                print(each_line)
                if keyword in each_line:
                    keyword_found = True
        if keyword_found:
            print("PASS: Keyword Found", keyword)
            return True
        else:
            print("FAIL:Keyword NOT Found", keyword)
            return False