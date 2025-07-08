import unittest
import subprocess
import os
env = os.environ.copy()


class test_suit_dlsps_cases(unittest.TestCase):
   
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
    unittest.main()