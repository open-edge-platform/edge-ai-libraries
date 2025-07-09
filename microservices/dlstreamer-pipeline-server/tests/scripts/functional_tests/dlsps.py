import subprocess
import os
import time
import unittest
import dlsps_utils as dlsps_module 
from configs import *

JSONPATH = os.path.dirname(os.path.abspath(__file__)) + '/../configs/dlsps_config.json'


class test_dlsps_cases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = os.path.dirname(os.path.abspath(__file__))
        cls.dlsps_utils = dlsps_module.dlsps_utils()

    def test_dlsps(self):
        test_case = os.environ['TEST_CASE']
        key, value = self.dlsps_utils.json_reader(test_case, JSONPATH)
        self.dlsps_utils.change_docker_compose_for_standalone()
        self.dlsps_utils.change_config_for_dlsps_standalone(value)
        self.dlsps_utils.common_service_steps_dlsps()
        self.dlsps_utils.execute_curl_command(value)
        time.sleep(5)
        self.assertTrue(self.dlsps_utils.container_logs_checker_dlsps("dlsps",test_case,value))

        
    @classmethod
    def tearDownClass(self):
        os.chdir('{}'.format(self.dlsps_utils.dlsps_path))
        subprocess.run('docker compose down -v', shell=True, executable='/bin/bash', check=True)
        subprocess.run('git checkout docker-compose.yml', shell=True, executable='/bin/bash', check=True)
        os.chdir('{}'.format(self.dlsps_utils.dlsps_path + "/../configs/default"))
        subprocess.run('git checkout config.json', shell=True, executable='/bin/bash', check=True)
        time.sleep(5)
