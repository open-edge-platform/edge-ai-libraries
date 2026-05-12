#
# Apache v2 license
# Copyright (C) 2024-2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import unittest
import subprocess
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class test_suit_dlsps_cases(unittest.TestCase):
    """
    Test suite for executing DL Streamer Pipeline Server test cases.
    
    This class defines individual test cases that invoke functional tests 
    using the `nosetests3` framework. Each test case sets the appropriate 
    environment variable for the test case ID and executes the corresponding 
    functional test.
    """
    
    def setUp(self):
        """Set up test environment before each test."""
        self.env = os.environ.copy()
        
    def _run_test_command(self, command, test_case_id=None):
        """
        Execute test command with proper error handling.
        
        Args:
            command (str): Command to execute
            test_case_id (str): Test case identifier for environment variable
            
        Returns:
            int: Return code (0 for success, non-zero for failure)
        """
        try:
            if test_case_id:
                self.env["TEST_CASE"] = test_case_id
                logger.info(f"Running test case: {test_case_id}")
            else:
                logger.info("Running repository generation")
                
            ret = subprocess.call(command, shell=True, env=self.env, timeout=300)
            
            if ret == 0:
                logger.info(f"Test completed successfully")
            else:
                logger.error(f"Test failed with return code: {ret}")
                
            return ret
            
        except subprocess.TimeoutExpired:
            logger.error("Test timed out after 300 seconds")
            return 1
        except Exception as e:
            logger.error(f"Error executing test: {str(e)}")
            return 1

    def dlsps_repo(self):
        """Generate repository for DLSPS use case."""
        command = "nosetests3 --nocapture ../functional_tests/dlsps.py:generate_repo.test_generate_repo"
        return self._run_test_command(command)

    def TC_001_dlsps(self):
        """GVADETECT - Pallet defect detection gvadetect pipeline - default"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps001")

    def TC_002_dlsps(self):
        """Test case 002 for DLSPS"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps002")

    def TC_003_dlsps(self):
        """Test case 003 for DLSPS"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps003")

    def TC_023_dlsps(self):
        """Verify single JPG file for image analysis workload - CPU backend"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps023")

    def TC_024_dlsps(self):
        """Verify single JPG file for image analysis workload - dGPU backend"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps024")

    def TC_027_dlsps(self):
        """Verify Single h264 Video file for Video analysis workload - CPU backend with MQTT"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps027")

    def TC_028_dlsps(self):
        """Verify Single h264 Video file for Video analysis workload - dGPU backend with MQTT"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps028")

    def TC_064_dlsps(self):
        """Verify Multi instance for video analysis workload - CPU backend"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps064")

    def TC_065_dlsps(self):
        """Verify Multi instance for video analysis workload - dGPU backend"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps065")

    def TC_069_dlsps(self):
        """Validate CVLC based Input for backend - CPU"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps069")

    def TC_070_dlsps(self):
        """Validate CVLC based Input for backend - iGPU/dGPU"""
        command = "nosetests3 --nocapture -v ../functional_tests/dlsps.py:test_dlsps_cases.test_dlsps"
        return self._run_test_command(command, "dlsps070")


if __name__ == '__main__':
    """
    Entry point for executing the test suite.
    Runs all test cases defined in the test_suit_dlsps_cases class.
    """
    unittest.main()
