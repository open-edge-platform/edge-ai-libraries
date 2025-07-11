***Settings***
Documentation    This is the main test case file for DL Streamer Pipeline Server sanity tests.
Library          test_suit_dlsps_cases.py



***Keywords***

dlsps_Test_case_001
    [Documentation]     Verify gvadetect element for pallet defect detection model - default pipeline - gvametapublish destination - backend -CPU
    ${status}          TC_001_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_002
    [Documentation]     Verify gvadetect element for pallet defect detection model - default pipeline for RTSP Camera - appsink destination backend - CPU
    ${status}          TC_002_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}

dlsps_Test_case_003
    [Documentation]     Verify gvadetect element for pallet defect detection model - default pipeline - appsink destination backend - CPU
    ${status}          TC_003_dlsps
    Should Not Be Equal As Integers    ${status}    1
    RETURN         Run Keyword And Return Status    ${status}


***Test Cases***

#ALL the test cases related to dlsps usecase

dlsps_TC_001
    [Documentation]     Verify gvadetect element for pallet defect detection model - default pipeline - gvametapublish destination - backend -CPU
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_001
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_002
    [Documentation]     Verify gvadetect element for pallet defect detection model - default pipeline for RTSP Camera - appsink destination backend - CPU
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_002
    Should Not Be Equal As Integers    ${Status}    0

dlsps_TC_003
    [Documentation]     Verify gvadetect element for pallet defect detection model - default pipeline - appsink destination backend - CPU
    [Tags]      dlsps
    ${Status}    Run Keyword And Return Status   dlsps_Test_case_003
    Should Not Be Equal As Integers    ${Status}    0