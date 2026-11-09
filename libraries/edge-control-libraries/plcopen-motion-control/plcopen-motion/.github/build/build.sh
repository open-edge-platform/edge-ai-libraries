#!/bin/bash

apt-get update -qq
echo "Asia\nShanghai" | apt-get install -y tzdata
apt-get -qq install cmake git build-essential
apt-get -qq install lcov
apt-get -qq install python3-matplotlib python3-numpy python3-dev python3-tk

WORKDIR=$(pwd)

git clone -b v1.14.0 https://github.com/google/googletest.git
cd googletest
mkdir build
cd build
cmake .. -DBUILD_SHARED_LIBS=ON -DCMAKE_CXX_FLAGS="-std=c++11"
make
make install
 
cd $WORKDIR
git clone -b v0.9.2 https://github.com/pantor/ruckig.git
cd ruckig
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make
make install

cd $WORKDIR
mkdir build
cd build
cmake .. -DTEST=ON -DWITH_COV=ON -DPLOT=ON
make
