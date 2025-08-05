# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
if (FUZZ)
	cmake_minimum_required(VERSION 3.19)
	set(CMAKE_C_COMPILER "/usr/bin/clang")
	set(CMAKE_CXX_COMPILER "/usr/bin/clang++")
	set(CMAKE_BUILD_TYPE "RelWithDebug")

	# GoogleTest requires at least C++17
	set(CMAKE_CXX_STANDARD 17)
	set(FUZZTEST_FUZZING_MODE "on")

	set(INCLUDE_DIR ../../include/plc_rt_common.hpp)

	include_directories (${INCLUDE_DIR})

	find_library(
	  LIBSHM_LIBRARIES
	  NAMES shmringbuf
	  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib)
	find_path(
	  LIBSHM_INCLUDE_DIRS 
	  NAMES shmringbuf.h
	  HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include)
	  
	add_executable(rt_test rt.cpp)
	target_link_libraries(rt_test ${LIBSHM_LIBRARIES} -lpthread)

	add_executable(nrt_test nrt.cpp)
	target_link_libraries(nrt_test ${LIBSHM_LIBRARIES} -lpthread)

	install(TARGETS rt_test nrt_test
	  RUNTIME DESTINATION ${INSTALL_BINDIR}
	)

	add_subdirectory(fuzztest)
	enable_testing()
	include(GoogleTest)
	fuzztest_setup_fuzzing_flags()

	set(SRC ../src)
	include_directories(${SRC})

	add_executable(
	  fuzz_plcopen-databus
	  test-plcopen-databus_fuzztest.cpp
	)

	target_link_libraries(fuzz_plcopen-databus PRIVATE ${LIBSHM_LIBRARIES} ruckig -lpthread)

	link_fuzztest(fuzz_plcopen-databus)

	gtest_discover_tests(fuzz_plcopen-databus)

endif(FUZZ)

