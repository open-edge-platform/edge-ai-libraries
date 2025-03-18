cmake_minimum_required(VERSION 3.10)

project(LinuxSample VERSION 1.0.0)

set(OpenCV_STATIC OFF)
find_package(OpenCV 4.2.0)

add_library(${PROJECT_NAME} SHARED "xiris.cpp")

target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_14)

target_compile_definitions(${PROJECT_NAME}
	PUBLIC
		USE_OPENCV
)

target_include_directories(${PROJECT_NAME}
	PUBLIC
		"${WELDSDK_DIR}/include"
		"${PWD}"
)

target_link_libraries(${PROJECT_NAME}
	PUBLIC
		"${WELDSDK_DIR}/lib/libWeldSDK.so"
        "${WELDSDK_DIR}/lib/libXVideoStream.so"
		"${WELDSDK_DIR}/lib/libXAudioSDK.so"
		${OpenCV_LIBS}
        stdc++fs
		asound
		jack
)
