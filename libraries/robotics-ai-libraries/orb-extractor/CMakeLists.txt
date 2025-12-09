# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.10)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)
enable_testing()

project(orblze CXX)

set(APP "gpu_orb_ocvfree")
set(APP_CV "gpu_orb")

string(APPEND CMAKE_CXX_FLAGS " -fsycl")

if(WIN32)
set(CMAKE_GENERATOR_TOOLSET "Intel(R) oneAPI DPC++ Compiler 2024")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 /EHa")
else()
set(CMAKE_CXX_COMPILER icpx)
string(APPEND CMAKE_CXX_FLAGS " -fPIC")

# Simple Intel LLVM/SYCL compatibility: Remove -fcf-protection flags
if(CMAKE_CXX_COMPILER_ID STREQUAL "IntelLLVM" OR CMAKE_CXX_COMPILER MATCHES ".*icpx.*")
    message(STATUS "Intel LLVM compiler detected - filtering incompatible flags")
    
    # Simple function to remove -fcf-protection flags
    macro(remove_fcf_protection_from_var var_name)
        if(${var_name})
            string(REGEX REPLACE "-fcf-protection[^ ]*" "" ${var_name} "${${var_name}}")
            string(STRIP "${${var_name}}" ${var_name})
        endif()
    endmacro()
    
    # Apply to all relevant CMAKE variables
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS)
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS_DEBUG)
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS_RELEASE)
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS_RELWITHDEBINFO)
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS_MINSIZEREL)
    
    # Clean environment variables if they exist
    if(DEFINED ENV{CXXFLAGS})
        set(ENV{CXXFLAGS} "")
        message(STATUS "Cleared CXXFLAGS environment variable")
    endif()
    if(DEFINED ENV{CPPFLAGS})
        set(ENV{CPPFLAGS} "")
        message(STATUS "Cleared CPPFLAGS environment variable") 
    endif()
endif()
endif()

option(BUILD_ZEBIN_INSTALL_DIR "ZE Binary GENX ouput path")
set(ORBLZE_KERNEL_PATH_STRING ${BUILD_ZEBIN_INSTALL_DIR})
if (NOT BUILD_ZEBIN_INSTALL_DIR)
  set (ORBLZE_KERNEL_PATH_STRING "/usr/lib/x86_64-linux-gnu")
endif()
set (ORBLZE_VERSION_MAJOR 2025)
set (ORBLZE_VERSION_MINOR 12)
set (ORBLZE_VERSION_PATCH 1)
set (ORBLZE_VERSION_STRING "${ORBLZE_VERSION_MAJOR}.${ORBLZE_VERSION_MINOR}.${ORBLZE_VERSION_PATCH}")

message(${CMAKE_CURRENT_LIST_DIR})

file(GLOB_RECURSE HOST_SRC "src/*.cpp" "src/gpu/*.cpp")

add_compile_options(-Wpedantic -Werror)

# Handle Intel LLVM compiler specific warnings for SYCL compilation
if(CMAKE_CXX_COMPILER_ID STREQUAL "IntelLLVM" OR CMAKE_CXX_COMPILER MATCHES ".*icpx.*")
    add_compile_options(-Wno-option-ignored)
    message(STATUS "Added -Wno-option-ignored for Intel LLVM/SYCL compatibility")
endif()

# Handle ROS Jazzy compatibility
if(DEFINED ENV{ROS_DISTRO})
  if($ENV{ROS_DISTRO} STREQUAL "jazzy")
    message(STATUS "Detected ROS Jazzy - applying SYCL compatibility fixes")
  endif()
endif()

#add_definitions("-Wall -Wextra")

include_directories (
   ${CMAKE_CURRENT_LIST_DIR}/include
   ${RUNTIME_INC}
)

if(DEFINED ENV{LD_LIBRARY_PATH})
  string(COMPARE EQUAL "$ENV{LD_LIBRARY_PATH}" "" RESULT)
  if (NOT RESULT)
    string(REPLACE ":" ";" SEARCH_LIB_PATH $ENV{LD_LIBRARY_PATH})
  endif()
endif()


if(CMAKE_INCLUDE_PATH)
  set(CMAKE_REQUIRED_INCLUDES ${CMAKE_INCLUDE_PATH})
endif()

set(CMAKE_REQUIRED_INCLUDES)

# OpenCV
find_package(OpenCV 4.2 REQUIRED)
include_directories(${OpenCV_INCLUDE_DIRS})

add_subdirectory ("${CMAKE_SOURCE_DIR}/src/sycl_utils")

# Re-apply Intel LLVM flag filtering after dependencies (in case they added flags)
if(CMAKE_CXX_COMPILER_ID STREQUAL "IntelLLVM" OR CMAKE_CXX_COMPILER MATCHES ".*icpx.*")
    message(STATUS "Re-applying Intel LLVM flag filtering after dependencies")
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS)
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS_DEBUG)
    remove_fcf_protection_from_var(CMAKE_CXX_FLAGS_RELEASE)
    string(APPEND CMAKE_CXX_FLAGS " -Wno-option-ignored")
endif()

set(config_h ${CMAKE_SOURCE_DIR}/include/config.h)
configure_file(
  cmake/config.h.in
  ${config_h}
  )

if (CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_definitions(-DDEBUG_LOG=1)
endif()

add_library(${APP} SHARED ${HOST_SRC})
add_library(${APP_CV} SHARED ${HOST_SRC})

target_compile_definitions(${APP} PUBLIC -DOPENCV_FREE)

# Add -Wno-option-ignored for Intel LLVM builds to suppress warnings
if(CMAKE_CXX_COMPILER_ID STREQUAL "IntelLLVM" OR CMAKE_CXX_COMPILER MATCHES ".*icpx.*")
    target_compile_options(${APP} PRIVATE -Wno-option-ignored)
    target_compile_options(${APP_CV} PRIVATE -Wno-option-ignored)
endif()

message("Install path ${CMAKE_INSTALL_LIBDIR}")


install(TARGETS ${APP} ${APP_CV} SyclUtils
  EXPORT orblzeTargets
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR} )

install(DIRECTORY ${CMAKE_SOURCE_DIR}/include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR} FILES_MATCHING PATTERN "*.h*" )

target_link_libraries(${APP} ${CMAKE_DL_LIBS} SyclUtils)
target_link_libraries(${APP} -lpthread -lstdc++fs)
#target_link_libraries(${APP} ${OpenCV_LIBS})

target_link_libraries(${APP_CV} ${CMAKE_DL_LIBS} SyclUtils)
target_link_libraries(${APP_CV} -lpthread -lstdc++fs)
target_link_libraries(${APP_CV} ${OpenCV_LIBS})

# Generate a .pc file for pkg-config
set(PACKAGE_VERSION ${ORBLZE_VERSION_STRING})
configure_file(${CMAKE_SOURCE_DIR}/orblze.pc.in ${CMAKE_CURRENT_BINARY_DIR}/orblze.pc @ONLY)

install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/orblze.pc DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)

#Config.cmake', 'ConfigVersion.cmake' and 'Targets.cmake'
#
include(CMakePackageConfigHelpers)
message("Cmake path ${CMAKE_INSTALL_PREFIX}/${INSTALL_CMAKE_DIR}")

if(NOT DEFINED INSTALL_CMAKE_DIR)
  set(INSTALL_CMAKE_DIR ${CMAKE_INSTALL_LIBDIR}/cmake/orblze)
endif()

set(path_vars
  CONFIG_DIR_CONFIG
  INCLUDE_DIR_CONFIG
  LIB_DIR_CONFIG
  ORBLZE_KERNEL_PATH_STRING
  )

set(CONFIG_DIR_CONFIG   ${CMAKE_INSTALL_PREFIX}/${INSTALL_CMAKE_DIR})
set(LIB_DIR_CONFIG      ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR})
set(INCLUDE_DIR_CONFIG  ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_INCLUDEDIR})
set(config_file ${PROJECT_BINARY_DIR}/orblzeConfig.cmake)

# Configure 'Config.cmake' for a build tree
configure_package_config_file(
  orblzeConfig.cmake.in
  ${config_file}
  INSTALL_DESTINATION ${PROJECT_BINARY_DIR}
  PATH_VARS ${path_vars}
  NO_CHECK_REQUIRED_COMPONENTS_MACRO
  )

# Configure and install 'Config.cmake' for an install tree
set(CONFIG_DIR_CONFIG   ${CMAKE_INSTALL_PREFIX}/${INSTALL_CMAKE_DIR})
set(install_config_file ${PROJECT_BINARY_DIR}${CMAKE_FILES_DIRECTORY}/orblzeConfig.cmake )
configure_package_config_file(
  orblzeConfig.cmake.in
  ${install_config_file}
  INSTALL_DESTINATION ${CMAKE_INSTALL_PREFIX}/${INSTALL_CMAKE_DIR}
  PATH_VARS ${path_vars}
  NO_CHECK_REQUIRED_COMPONENTS_MACRO
  )

install(
  FILES ${install_config_file}
  DESTINATION ${INSTALL_CMAKE_DIR} COMPONENT Development
  )

# Configure 'Targets.cmake' for a build tree
export(TARGETS ${APP} ${APP_CV} SyclUtils
  FILE ${PROJECT_BINARY_DIR}/orblzeTargets.cmake
  )

# Configure and install 'Targets.cmake' for an install tree
install(EXPORT orblzeTargets
  FILE orblzeTargets.cmake
  DESTINATION ${INSTALL_CMAKE_DIR}
  COMPONENT Development
  )

# Configure 'ConfigVersion.cmake' for a build tree
set(config_version_file ${PROJECT_BINARY_DIR}/orblzeConfigVersion.cmake)
write_basic_package_version_file(
    ${config_version_file}
    VERSION ${ORBLZE_VERSION_STRING}
    COMPATIBILITY AnyNewerVersion
)
# ... and install for an install tree
install(
  FILES ${config_version_file}
  DESTINATION ${INSTALL_CMAKE_DIR} COMPONENT Development
  )


