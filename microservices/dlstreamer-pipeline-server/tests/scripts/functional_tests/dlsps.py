#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# 

import subprocess
import os
import time
import unittest
import dlsps_utils as dlsps_module 
from configs import *

JSONPATH = os.path.dirname(os.path.abspath(__file__)) + '/../configs/dlsps_config.json'


class test_dlsps_cases(unittest.TestCase):
    """
    Functional test cases for the DL Streamer Pipeline Server.

    This class uses the `dlsps_utils` module to configure, run, and validate
    the DL Streamer Pipeline Server. It includes setup, execution, and teardown
    steps for the tests.
    """

    @classmethod
    def setUpClass(cls):
        """
        Sets up the test environment before running the test cases.

        Initializes the `dlsps_utils` instance and sets the path for the test scripts.
        """
        cls.path = os.path.dirname(os.path.abspath(__file__))
        cls.dlsps_utils = dlsps_module.dlsps_utils()

    def test_dlsps(self):
        """
        Executes the functional test for the DL Streamer Pipeline Server.

        Steps:
        1. Reads the test case configuration from a JSON file.
        2. Updates the Docker Compose and DL Streamer configuration.
        3. Builds and runs the DL Streamer Pipeline Server.
        4. Sends a POST request to start a pipeline and validates its status.
        5. Checks container logs for expected keywords.

        Assertions:
            Asserts that all expected keywords are found in the container logs.

        Environment Variables:
            TEST_CASE (str): Name of the test case to execute.
        """
        test_case = os.environ['TEST_CASE']
        key, value = self.dlsps_utils.json_reader(test_case, JSONPATH)
        self.dlsps_utils.change_docker_compose_for_standalone()
        self.dlsps_utils.change_config_for_dlsps_standalone(value)
        self.dlsps_utils.common_service_steps_dlsps()
        self.dlsps_utils.execute_curl_command(value)
        time.sleep(5)
        self.assertTrue(self.dlsps_utils.container_logs_checker_dlsps(test_case,value))

        
    @classmethod
    def tearDownClass(cls):
        """
        Cleans up the test environment after running the test cases.

        Steps:
        1. Stops and removes Docker containers and volumes.
        2. Restores the original `docker-compose.yml` and `config.json` files.
        """
        os.chdir('{}'.format(cls.dlsps_utils.dlsps_path))
        subprocess.run('docker compose down -v', shell=True, executable='/bin/bash', check=True)
        subprocess.run('git checkout docker-compose.yml', shell=True, executable='/bin/bash', check=True)
        os.chdir('{}'.format(cls.dlsps_utils.dlsps_path + "/../configs/default"))
        subprocess.run('git checkout config.json', shell=True, executable='/bin/bash', check=True)
        time.sleep(5)
