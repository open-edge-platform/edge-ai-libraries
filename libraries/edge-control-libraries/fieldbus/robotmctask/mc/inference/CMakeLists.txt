# Define the library's sources
set(INFERENCE_SOURCES 
    inference.cpp
    inference_config.cpp
    rl_inference/rl_stand_inference.cpp
    rl_inference/rl_inference_dummy.cpp
)

include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../
    ${OpenVINO_INCLUDE_DIRS}
)

# Add the shared library target
add_library(mc_inference SHARED ${INFERENCE_SOURCES})

target_link_libraries(mc_inference
    yaml-cpp
    openvino::runtime
)

set_target_properties(mc_inference PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")

# Specify include directories for the library (if needed)
target_include_directories(mc_inference PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
