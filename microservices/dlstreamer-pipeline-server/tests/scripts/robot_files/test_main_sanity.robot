*** Settings ***
Documentation    This is main test case file.
Library          test_suit_dlsps_cases.py

*** Variables ***
${IS_OPEN_EDGE}    false

*** Keywords ***
generate_repo_for_dlsps
    [Documentation]    Generate repo for dlsps usecase
    ${status}=    dlsps_repo
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_023
    [Documentation]    Verify single JPG file for image analysis workload. E2E Test case for backend - CPU - evi_kpi_test_workload1_1
    ${status}=    TC_023_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_024
    [Documentation]    Verify single JPG file for image analysis workload. E2E Test case for backend - dGPU - evi_kpi_test_workload1_1
    ${status}=    TC_024_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_027
    [Documentation]    Verify Single h264 Video file for Video analysis workload. E2E test case for backend - CPU - evi_kpi_test_workload2_1 for MQTT publisher
    ${status}=    TC_027_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_028
    [Documentation]    Verify Single h264 Video file for Video analysis workload. E2E test case for backend - dGPU - evi_kpi_test_workload2_1 for MQTT publisher
    ${status}=    TC_028_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_064
    [Documentation]    Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - CPU
    ${status}=    TC_064_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_065
    [Documentation]    Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - dGPU
    ${status}=    TC_065_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_001
    [Documentation]    GVADETECT - Pallet defect detection gvadetect pipeline - default
    ${status}=    TC_001_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_069
    [Documentation]    Validate CVLC based Input for backend : CPU
    ${status}=    TC_069_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

dlsps_Test_case_070
    [Documentation]    Validate CVLC based Input for backend : iGPU/dGPU
    ${status}=    TC_070_dlsps
    Should Be Equal As Integers    ${status}    0
    RETURN    ${status}

*** Test Cases ***
dlsps_repo
    [Documentation]    Generate repo for dlsps usecase
    [Tags]    dlsps
    generate_repo_for_dlsps

dlsps_TC_023
    [Documentation]    Verify single JPG file for image analysis workload. E2E Test case for backend - CPU - evi_kpi_test_workload1_1
    [Tags]    dlsps
    dlsps_Test_case_023

dlsps_TC_024
    [Documentation]    Verify single JPG file for image analysis workload. E2E Test case for backend - dGPU - evi_kpi_test_workload1_1
    [Tags]    dlsps
    dlsps_Test_case_024

dlsps_TC_027
    [Documentation]    Verify Single h264 Video file for Video analysis workload. E2E test case for backend - CPU - evi_kpi_test_workload2_1 for MQTT publisher
    [Tags]    dlsps
    dlsps_Test_case_027

dlsps_TC_028
    [Documentation]    Verify Single h264 Video file for Video analysis workload. E2E test case for backend - dGPU - evi_kpi_test_workload2_1 for MQTT publisher
    [Tags]    dlsps
    dlsps_Test_case_028

dlsps_TC_064
    [Documentation]    Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - CPU
    [Tags]    dlsps
    dlsps_Test_case_064

dlsps_TC_065
    [Documentation]    Verify Multi instance for video analysis workload for video input - 4/8 streams - till we get 5 to 10 AVG FPS. Backend - dGPU
    [Tags]    dlsps
    dlsps_Test_case_065

dlsps_TC_001
    [Documentation]    GVADETECT - Pallet defect detection gvadetect pipeline - default
    [Tags]    dlsps
    dlsps_Test_case_001

dlsps_TC_069
    [Documentation]    Validate CVLC based Input for backend : CPU
    [Tags]    dlsps
    dlsps_Test_case_069

dlsps_TC_070
    [Documentation]    Validate CVLC based Input for backend : iGPU/dGPU
    [Tags]    dlsps
    dlsps_Test_case_070
