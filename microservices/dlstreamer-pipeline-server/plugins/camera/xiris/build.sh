#!/bin/sh

# The install path for Xiris WeldSDK, needed for including headers and linking libs
WELDSDK_DIR=/opt/xiris/weldsdk

# Makes a build directory for CMake to generate its files in
mkdir build
cd ./build

# Run CMake to generate the build configuration, this generates a makefile
cmake -DWELDSDK_DIR=$WELDSDK_DIR ..

# Build the program using make
make