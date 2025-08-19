#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
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
        

if __name__ == '__main__':
    """
    Entry point for executing the test suite.
    Runs all test cases defined in the `test_suit_dlsps_cases` class.
    """
    unittest.main()