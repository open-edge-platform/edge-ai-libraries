# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.10)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)
enable_testing()

project(orblze CXX)

set(APP "gpu_orb_ocvfree")
set(APP_CV "gpu_orb")

option(BUILD_ZEBIN_INSTALL_DIR "ZE Binary GENX ouput path")
set(ORBLZE_KERNEL_PATH_STRING ${BUILD_ZEBIN_INSTALL_DIR})
if (NOT BUILD_ZEBIN_INSTALL_DIR)
  set (ORBLZE_KERNEL_PATH_STRING "/usr/lib/x86_64-linux-gnu")
endif()
set (ORBLZE_VERSION_MAJOR 2023)
set (ORBLZE_VERSION_MINOR 1)
set (ORBLZE_VERSION_PATCH 1)
set (ORBLZE_VERSION_STRING "${ORBLZE_VERSION_MAJOR}.${ORBLZE_VERSION_MINOR}.${ORBLZE_VERSION_PATCH}")

message(${CMAKE_CURRENT_LIST_DIR})

file(GLOB_RECURSE KERNEL_SRC "src/*_genx.cpp")
file(GLOB_RECURSE HOST_SRC "src/*.cpp" "src/gpu/*.cpp")

foreach(kernel ${KERNEL_SRC})
    list(REMOVE_ITEM HOST_SRC "${kernel}")
endforeach()

add_compile_options(-Wpedantic -Werror)

#add_definitions("-Wall -Wextra")

include_directories (
   ${CMAKE_CURRENT_LIST_DIR}/include
   ${RUNTIME_INC}
)

find_program(OCLOC ocloc  REQUIRED)
find_program(CMC cmc REQUIRED)

if(DEFINED ENV{LD_LIBRARY_PATH})
  string(COMPARE EQUAL "$ENV{LD_LIBRARY_PATH}" "" RESULT)
  if (NOT RESULT)
    string(REPLACE ":" ";" SEARCH_LIB_PATH $ENV{LD_LIBRARY_PATH})
  endif()
endif()

find_library(L0_LIB_PATH
  NAMES ze_loader
  PATHS ${SEARCH_LIB_PATH})
if(NOT L0_LIB_PATH)
  message(FATAL_ERROR
    "Level Zero loader is not found. "
    "You may need to install oneAPI Level Zero loader to fix this issue.")
else()
  message(STATUS
    "Level Zero loader is found at ${L0_LIB_PATH}")
endif()

if(CMAKE_INCLUDE_PATH)
  set(CMAKE_REQUIRED_INCLUDES ${CMAKE_INCLUDE_PATH})
endif()

include(CheckIncludeFileCXX)
check_include_file_cxx(level_zero/ze_api.h LO_CORE_INC_FOUND)
check_include_file_cxx(level_zero/zet_api.h LO_TOOLS_INC_FOUND)
check_include_file_cxx(level_zero/zes_api.h LO_SYSMAN_INC_FOUND)
check_include_file_cxx(level_zero/layers/zel_tracing_api.h LO_LAYERS_INC_FOUND)
if ((NOT LO_CORE_INC_FOUND) OR (NOT LO_TOOLS_INC_FOUND) OR (NOT LO_LAYERS_INC_FOUND) OR (NOT LO_SYSMAN_INC_FOUND))
  message(STATUS "Level Zero headers are not found, will be downloaded automatically")
endif()
set(CMAKE_REQUIRED_INCLUDES)

# OpenCV
find_package(OpenCV 4.2 REQUIRED)
include_directories(${OpenCV_INCLUDE_DIRS})

option(BUILD_TARGET_PLATFORM "ZE Binary GENX Target platform")
if (NOT BUILD_TARGET_PLATFORM)
  set(GPU gen12lp)
else()
  set(GPU "${BUILD_TARGET_PLATFORM}")
endif()

option(BIN "generate kernel Intermediate file" OFF)

option(TARGET_PLATFORM_LIST "Spirv GENX Target platform list")
if (NOT TARGET_PLATFORM_LIST)
    set(MARCHLIST "gen9;gen11lp;gen12lp;mtl;dg2")
else()
    string(REPLACE "," ";" MARCHLIST ${TARGET_PLATFORM_LIST})
endif()

foreach(kernel ${KERNEL_SRC})
  
  get_filename_component(kernelfilename ${kernel} NAME_WE)
        
  foreach(genx ${MARCHLIST})

    # SPIRV need to match ocloc acronyms
    if (genx STREQUAL gen9)
      set(oclocacronym gen9)
    elseif (genx STREQUAL gen11lp)
      set(oclocacronym gen11)
    elseif (genx STREQUAL gen12lp)
      set(oclocacronym gen12lp)
    elseif (genx STREQUAL dg2)
      set(oclocacronym xehpg)
    elseif (genx STREQUAL mtl)
      set(oclocacronym xelpg)
    else()
      set(oclocacronym genXe)
    endif()

    list(APPEND KERNEL_SPV "${CMAKE_CURRENT_BINARY_DIR}/${kernelfilename}_${oclocacronym}.spv")

    if(oclocacronym STREQUAL genXe)

      add_custom_command(
	OUTPUT ${kernelfilename}_${oclocacronym}.spv
	COMMAND ${CMC} -emit-spirv -binary-format ze -march=gen12lp -o ${kernelfilename}_${oclocacronym}.spv --  ${kernel}
	DEPENDS ${kernel}
	COMMENT "Generate ${kernel} .spv"
	)
      
      message(STATUS "Fat ${kernelfilename} level-zero binary for ALL intel GPU ")
      list(APPEND KERNEL_BIN "${CMAKE_CURRENT_BINARY_DIR}/${kernelfilename}.bin")

      add_custom_command(
        OUTPUT ${kernelfilename}.bin
        COMMAND ${OCLOC} compile -spirv_input -file ${kernelfilename}_${oclocacronym}.spv -output ${kernelfilename}.bin -force_stos_opt -device :xe -output_no_suffix
        DEPENDS  ${kernelfilename}_${oclocacronym}.spv
        COMMENT "Generate ${kernel} level-zero binary"
	)

    else()
    
      add_custom_command(
	OUTPUT ${kernelfilename}_${oclocacronym}.spv
	COMMAND ${CMC} -emit-spirv -binary-format ze -march=${genx} -o ${kernelfilename}_${oclocacronym}.spv --  ${kernel}
	DEPENDS ${kernel}
	COMMENT "Generate ${kernel} .spv"
	)

      if (genx STREQUAL ${GPU})

	message(STATUS "Individual ${kernelfilename} level-zero binary for: ${GPU}")
	list(APPEND KERNEL_BIN "${CMAKE_CURRENT_BINARY_DIR}/${kernelfilename}.bin")

	add_custom_command(
          OUTPUT ${kernelfilename}.bin
          COMMAND ${OCLOC} compile -spirv_input -file ${kernelfilename}_${oclocacronym}.spv -output ${kernelfilename}.bin -force_stos_opt -device ${oclocacronym} -output_no_suffix
          DEPENDS  ${kernelfilename}_${oclocacronym}.spv
          COMMENT "Generate ${kernel} level-zero binary"
	  )

      endif()

    endif()

  endforeach()
  
endforeach()

set(config_h ${CMAKE_SOURCE_DIR}/include/config.h)
configure_file(
  cmake/config.h.in
  ${config_h}
  )

if (CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_definitions(-DDEBUG_LOG=1)
endif()

add_library(${APP} SHARED ${HOST_SRC} ${KERNEL_BIN} ${KERNEL_SPV}  )
add_library(${APP_CV} SHARED ${HOST_SRC} ${KERNEL_BIN} )

target_compile_definitions(${APP} PUBLIC -DOPENCV_FREE)

message("Install path ${CMAKE_INSTALL_LIBDIR}")

install(TARGETS ${APP} ${APP_CV}
  EXPORT orblzeTargets
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR} )

install(FILES ${KERNEL_BIN} DESTINATION ${CMAKE_INSTALL_LIBDIR})

install(DIRECTORY ${CMAKE_SOURCE_DIR}/include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR} FILES_MATCHING PATTERN "*.h*" )

if(MSVC)
	target_include_directories(${APP} PRIVATE $ENV{CSDK_DIR}\\runtime\\level_zero\\include $ENV{SYCL_BUNDLE_ROOT}\\compiler\\include)
endif()

target_link_libraries(${APP} ${CMAKE_DL_LIBS} ${L0_LIB_PATH})
target_link_libraries(${APP} -lpthread -lstdc++fs)

target_link_libraries(${APP_CV} ${CMAKE_DL_LIBS} ${L0_LIB_PATH})
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
export(TARGETS ${APP}
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
