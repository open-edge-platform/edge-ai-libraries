# RTmotion
C++ library of PLCopen motion control function blocks

## Documentation
The documentation can be compiled to `doc` subfolder through the commands:
```bash
sudo apt install graphviz

doxygen ./Doxyfile
```

Open `doc/html/index.html` to check the documentation.

## Dependency
Install system depends:
```bash
sudo apt-get -qq install cmake git build-essential
```

Install Ruckig:
```bash
git clone -b v0.9.2 https://github.com/pantor/ruckig.git
cd ruckig
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make
make install
```

## Build
```bash
cd <RTmotion_root_directory>

mkdir build && cd build

# If build on Ubuntu Linux, run the next command
cmake ..

# If build on PREEMPT Linux, run the next command
cmake ..

# If build on Xenomai, run the next command
cmake .. -DXENOMAI_DIR=<path_to_xenomai_directory>

make && sudo make install

# Try **sudo ldconfig** after installation if meet any problem related to library file missing.
```
> Note: Install **googletest** then add `-DTEST=ON` or `-DPLOT=ON` to CMake commands if need to do [Unit Test](#unit-test) or plot the result. Check Unit Test below for details.

## Run Minimum Example
```bash
<build folder>/src/multi-axis
```

## Run Evaluation Example
Running the evaluation program using the following commands:

```bash
<build folder>/src/multi-axis-monitor
```

> Note: This evaluation program enables a MC_MoveRelative function block running in 1ms real-time cycle. The function block will be re-triggered everytime it finished its task. It can be stopped by `Ctrl+C`.

## Unit Test
Googletest is used as the test framework. Therefore, if test running is desired, follow the commands below to install `gtest` at first.
```bash
sudo apt install googletest
```
or

```bash
git clone -b v1.14.0 https://github.com/google/googletest.git
cd googletest
mkdir build
cd build
cmake .. -DBUILD_SHARED_LIBS=ON -DCMAKE_CXX_FLAGS="-std=c++11"
make
make install
  ```

> Note: In order to build the tests, add the argument `-DTEST=ON` to CMake commands.

To enable the plotting in the test, add CMake argument `-DPLOT=ON` and install the dependencies below:

```bash
sudo apt-get install python3-matplotlib python3-numpy python3-dev
```

Run unit tests by following the commands below:
- On-line S-Curve Algorithm Test:
  ```bash
  <build folder>/test/online_scurve_test
  ```

- Trjactory Planner Test:
  ```bash
  <build folder>/test/planner_test
  ```

- Function Block Test:
  ```bash
  <build folder>/test/function_block_test
  ```

## Link to the library
By default the header files are installed to `/usr/local/include/RTmotion/`, the library file `libRTmotion.so` are installed to `/use/local/lib`.