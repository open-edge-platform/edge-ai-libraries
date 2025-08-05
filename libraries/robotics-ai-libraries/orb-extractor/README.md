# ORB Feature Extractor - applications.robotics.mobile.orb-extractor

Description
-----------------------------------------------------------------------------
The ORB feature extractor sample application demonstrates its functionality on both CPU and GPU. The ORB feature extractor is based on the OpenVSLAM version.

https://github.com/OpenVSLAM-Community/openvslam

The ORB feature extractor comprises various computer vision (CV) kernels such as resize, Gaussian, FAST, compute descriptor, and orientation, along with non-CV functions like distribute_keypoints_via_tree.

All the CV-related kernels are offloaded to the Intel GPU using the oneAPI Level Zero interface, and the GPU kernels are written using C-for-Metal. Non-CV functions run on the CPU.

For more information about the oneAPI Level Zero interface, refer to the link below.

https://spec.oneapi.io/level-zero/latest/index.html

For more informaton of C-for-Metal, refer to link below.

https://01.org/c-for-metal-development-package


System Requirements for building and running the sample
-----------------------------------------------------------------------------

### Require Ubuntu 20.04
Follow the link below.
https://ubuntu.com/tutorials/install-ubuntu-desktop#1-overview

### Kernel version 5.8.0 or greater

#### To install latest Ubuntu linux kernel

```bash  
sudo apt-get upgrade linux-image-generic 
```

#### To install a specific kernel version (alternatively)
 ```bash
wget https://raw.githubusercontent.com/pimlie/ubuntu-mainline-kernel.sh/master/ubuntu-mainline-kernel.sh
```
```bash
chmod +x ubuntu-mainline-kernel.sh
```
```bash
./ubuntu-mainline-kernel.sh -i <kernel version to install>
```

### Install build tools
```bash
sudo apt install build-essential cmake
```

### Install Level Zero runtime
Follow the link below.
https://dgpu-docs.intel.com/installation-guides/ubuntu/ubuntu-focal-legacy.html

### Install OpenCV 4.2
The library only depends on OpenCV for some of cv types like cv::KeyPoint, cv::Mat,
and function like cv::getGaussianKernel.  

Follow the link below.
https://linuxize.com/post/how-to-install-opencv-on-ubuntu-20-04/

### Install C for Metal Development Package
```bash
wget https://01.org/sites/default/files/downloads/cmsdk20211028.zip
unzip cmsdk20211028.zip
cd cm_sdk_20211028
source setupenv.sh
```

### Build the library
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries
cd edge-ai-libraries/libraries/orb-extractor
mkdir build
cd build
cmake -DBUILD_TARGET_PLATFORM=<platform name> -DCMAKE_BUILD_TYPE=<Release/Debug> -DCMAKE_INSTALL_PATH=<path to installation folder> ../ 
# For ex: use cmake -DBUILD_TARGET_PLATFORM=tgllp -DCMAKE_BUILD_TYPE=Release ../ to build for tigerlake
# or cmake ../ to build for current platform
make -j8
```
### Install library

***Note*** use sudo if installing into default location of /usr. Otherwise, not recommended.
```bash
sudo make install
```
### Build the sample
```bash
cd ../samples
mkdir build
cd build
cmake ../
make -j8
```
### Run the sample
```bash
./feature_extract
```
### Build unit tests
```bash
# Build the library
cd ../tests
mkdir build
cd build
cmake ../
make -j8
```
### Run the test
```bash
./gaussTest
./resizeTest
./fastTest
./orbdescTest
./stereoTest
```

### Adjusting for latency and CPU util
```bash
export CPU_SLEEP_TIME=<sleep duration in microseconds>
```
***Note*** Higher sleep value leads to higher latency & reduced CPU util and vice versa
