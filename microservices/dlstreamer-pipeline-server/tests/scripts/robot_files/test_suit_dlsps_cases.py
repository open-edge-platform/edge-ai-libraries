#
# Apache v2 license
# Copyright (C) 2024-2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# 

import unittest
import subprocess
import os
env = os.environ.copy()


class test_suit_dlsps_cases(unittest.TestCase):
    """
    Test suite for executing DL Streamer Pipeline Server test cases.

    This class defines individual test cases that invoke functional tests
    using the `nosetests3` framework. Each test case sets the appropriate
    environment variable for the test case ID and executes the corresponding
    functional test.
    """
    def dlsps_repo(self):
        ret = subprocess.call("nosetests3 --nocapture ../functional_tests/dlsps.py:generate_repo.test_generate_repo", shell=True)
        return ret
    def TC_001_dlsps(self):
        env["TEST_CASE"] = "dlsps001"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
      
    def TC_002_dlsps(self):
        env["TEST_CASE"] = "dlsps002"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    
    def TC_003_dlsps(self):
        env["TEST_CASE"] = "dlsps003"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    def TC_023_dlsps(self):
        env["TEST_CASE"] = "dlsps023"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    
    def TC_024_dlsps(self):
        env["TEST_CASE"] = "dlsps024"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    def TC_027_dlsps(self):
        env["TEST_CASE"] = "dlsps027"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret

    def TC_028_dlsps(self):
        env["TEST_CASE"] = "dlsps028"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    def TC_064_dlsps(self):
        env["TEST_CASE"] = "dlsps064"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    
    def TC_065_dlsps(self):
        env["TEST_CASE"] = "dlsps065"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    def TC_069_dlsps(self):
        env["TEST_CASE"] = "dlsps069"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
    
    def TC_070_dlsps(self):
        env["TEST_CASE"] = "dlsps070"
        ret = subprocess.call("nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps", shell=True, env=env)
        return ret
if __name__ == '__main__':
    """
    Entry point for executing the test suite.
    Runs all test cases defined in the `test_suit_dlsps_cases` class.
    """
    unittest.main()
