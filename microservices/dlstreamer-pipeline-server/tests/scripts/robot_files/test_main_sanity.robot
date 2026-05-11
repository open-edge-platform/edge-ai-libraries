***Settings***
Documentation    This is main test case file.
Library          test_suit_dlsps_cases.py

***Variables***
${IS_OPEN_EDGE}    false


***Keywords***

generate_repo_for_dlsps
    [Documentation]    Generate repo for dlsps usecase
    ${status}          dlsps_repo
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_023
    [Documentation]     Verify single JPG file for image analysis workload. E2E Test case for backend - CPU - evi_kpi_test_workload1_1 
    ${status}          TC_023_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_024
    [Documentation]     Verify single JPG file for image analysis workload. E2E Test case for backend - dGPU - evi_kpi_test_workload1_1 
    ${status}          TC_024_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_027
    [Documentation]     Verify Single h264 Video  file for Video analysis workload.  E2E test case for backend - CPU - evi_kpi_test_workload2_1 for MQTT publisher
    ${status}          TC_027_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_028
    [Documentation]     Verify Single h264 Video  file for Video analysis workload.  E2E test case for backend - dGPU - evi_kpi_test_workload2_1 for MQTT publisher
    ${status}          TC_028_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_064
    [Documentation]     Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - CPU
    ${status}          TC_064_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_065
    [Documentation]     Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - dGPU
    ${status}          TC_065_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_001
    [Documentation]     GVADETECT - Pallet defect detection gvadetect pipeline - default 
    ${status}          TC_001_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_069
    [Documentation]     Validate CVLC based Input for backend : CPU
    ${status}          TC_069_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_070
    [Documentation]     Validate CVLC based Input for backend : iGPU/dGPU
    ${status}          TC_070_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}





***Test Cases***

#ALL the test cases related to dlsps usecase

dlsps_repo
    [Documentation]    Generate repo for dlsps usecase
    [Tags]    dlsps
     ${Status}    Run Keyword And Return Status   generate_repo_for_dlsps
     Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_023
    [Documentation]   Verify single JPG file for image analysis workload. E2E Test case for backend - CPU - evi_kpi_test_workload1_1 
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_023
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_024
    [Documentation]   Verify single JPG file for image analysis workload. E2E Test case for backend - dGPU - evi_kpi_test_workload1_1 
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_024
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_027
    [Documentation]   Verify Single h264 Video  file for Video analysis workload.  E2E test case for backend - CPU - evi_kpi_test_workload2_1 for MQTT publisher
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_027
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_028
    [Documentation]   Verify Single h264 Video  file for Video analysis workload.  E2E test case for backend - dGPU - evi_kpi_test_workload2_1 for MQTT publisher
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_028
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_064
    [Documentation]    Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - CPU
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_064
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_065
    [Documentation]    Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - dGPU
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_065
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_001
    [Documentation]    GVADETECT - Pallet defect detection gvadetect pipeline - default
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_001
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_069
    [Documentation]    Validate CVLC based Input for backend : CPU
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_069
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_070
    [Documentation]    Validate CVLC based Input for backend : iGPU/dGPU
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_070
    Should Not Be Equal As Integers    ${Status}    0