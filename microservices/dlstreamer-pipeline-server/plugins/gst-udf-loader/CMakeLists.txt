# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: MIT

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

project(EII_Loader)

cmake_minimum_required (VERSION 3.1)


if(NOT(UNIX))
    message(FATAL_ERROR "Only UNIX supported")
endif()

set(PLUGIN_VERSION 1)

add_definitions(-DPLUGIN_VERSION="${PLUGIN_VERSION}")
add_definitions(-DPACKAGE="eii-udf-loader")
add_definitions(-DPACKAGE_NAME="GStreamer UDF loader element")
add_definitions(-DGST_PACKAGE_ORIGIN="to_be_added")
add_definitions(-DPLUGIN_LICENSE="MIT/X11")

# Set C++ version
set(CMAKE_CXX_STANDARD 14)

# Set CFLAGS for C/C++
set(CMAKE_C_FLAGS "-fPIE -fPIC -O2 -Wall -pedantic -fstack-protector-strong -D_FORTIFY_SOURCE=2")
set(CMAKE_CXX_FLAGS "${CMAKE_C_FLAGS}")

# Set LDFLAGS
set(CMAKE_SHARED_LINKER_FLAGS "-z noexecstack -z relro -z now")


set (PLUGINS_INSTALL_PATH lib)


add_subdirectory(gst_plugin)