# Userspace EtherCAT Master Stack

## Introduction

The EtherCAT Master User Space Stack is an optimized version of the IgH EtherCAT Master Stack designed to run in user space on systems with the Preempt RT patch. This optimization eliminates the need for ioctl system calls, which can introduce latency, thereby improving performance. By maintaining all APIs from the original IgH EtherCAT Master Stack, this user space stack ensures compatibility with existing EtherCAT application programs, allowing for seamless integration and transition.

Key features of the EtherCAT Master User Space Stack include:

- **Latency Improvement:** By avoiding ioctl system calls, the stack reduces latency, which is crucial for real-time applications.
- **Compatibility:** The stack retains all APIs from the original IgH EtherCAT Master Stack, ensuring that existing EtherCAT applications can run without modification.
- **Containerization:** The stack is designed to be easily containerized, facilitating deployment in modern software environments that use containers for isolation and scalability.
- **Multiple Master Support:** The stack supports multiple EtherCAT masters, allowing for complex network configurations and improved scalability.

Overall, this user space stack provides a robust solution for real-time EtherCAT applications, offering improved performance and flexibility while maintaining compatibility with existing software.

## Architecture Overview

The architecture is as following:

<p>
    <img src="images/ethercat_usermode.png" alt="Userspace EtherCAT Master Stack Architecture" title="Userspace EtherCAT Master Stack Architecture" style="height:65%;width:65%;">
</p>

Two mode options are supported as needed: 
* **Daemon Mode** builds EtherCAT master module as daemon application, which can run as standalone and provides one or more EtherCAT master instances, `Application Interface` and IPC service for multiple process communication. But it need at least 2x cores.
* **Library Mode** builds EtherCAT master module as library, which can be linked as dynamic library by the application. IPC service will only support on non-rt application(e.g. `ethercat` utility tool). It only need one core for one master instance.


## Getting Started

### Installing Dependencies (Oneshot Time)

Run the following packages to install dependence packages for building on Ubuntu:

```shell
    sudo apt-get install autoconf automake git libtool build-essential libmodbus5 libmodbus-dev 
```

To install the required DPDK packages on Ubuntu, run:

```shell
    sudo apt-get install dpdk dpdk-dev libdpdk-dev
```

### Installing Patches (Oneshot Time)

Firstly, pull submodule locally using ``git``:

```shell
    git submodule init
    git submodule update
```

Run the script ``install_etherlab_patched.sh`` to apply optimization patches in ``ighethercat`` folder, the patch list is defined in ``patches/ighethercat.scc``.

```shell
    ./install_ethercatlab_patched.sh patches/ighethercat.scc
```

### Building EtherCAT Stack

Following with below commands to build EtherCAT Master Stack:

**For Daemon Mode**:

```shell
   cd ighethercat
   ./bootstrap
   ./configure --enable-sii-assign --disable-eoe --enable-hrtimer --disable-cycles --enable-usermode --enable-daemon
   make
```

**For Library Mode**:

```shell
   cd ighethercat
   ./bootstrap
   ./configure --enable-sii-assign --disable-eoe --enable-hrtimer --disable-cycles --enable-usermode --disable-daemon
   make
```

### Installing The Software

The below commands have to entered as root, which will install the EtherCAT header, scripts, libraries and userspace tool to the ``prefix`` path.

```shell
   make install
```

### Configuring EtherCAT Device

The ``ecrt.conf`` file located at ``/etc/sysconfig/`` is a crucial configuration file for setting up EtherCAT master nodes. This file contains the necessary configuration variables to operate one or more EtherCAT masters effectively. Make sure to customize below parameters based on your hardware setup and operational needs.

The following describes the configuration parameters that can be defined within the **ethercat** section:

**node_id:**

   This parameter assigns a unique identifier to each EtherCAT master node. The ``node_id`` is essential for distinguish between different nodes, especially in setups involving multiple masters or when managing several EtherCAT networks. Each node should have a distinct ID to ensure proper communication and control within the network.

**master_mac:**

   This specifies the MAC address of the network interface card (NIC) that the EtherCAT master will use for communication. The MAC address is a unique identifier for network devices, ensuring that each master can be correctly identified on the network. If you are using multiple master within a single EtherCAT application, you can register multiple MAC addresses as a list. This allows for flexible configurations and supports complex network setups.

**debug_level:**

   This setting controls the verbosity of debug information output by the EtherCAT master. A debug level of ``0`` means no debug information will be printed, which is suitable for production environments where performance is prioritized. Higher debug levels(up to ``2``) provide more detailed logs, which can be invaluable during development or troubleshooting to understand the system's behavior and diagnose issues.

**drv_argv:**

   This parameter allows you to add extra Environment Abstraction Layer(**EAL**) for the Data Plane Development Kit(**DPDK**) framework. **DPDK** is a set of libraries and drivers for fast packet processing, and **EAL** parameters help configure its operation. For detailed information on available **EAL** parameters and their usage, you can refer to the official **DPDK** documentation at [EAL parameters](https://doc.dpdk.org/guides/linux_gsg/linux_eal_parameters.html). This flexibility enables you to optimize the performance and behavior of the EtherCAT master according to your specific requirements.

### Binding VFIO driver

Before binding VFIO driver, Need to ensure kernel enabling following config options on ``vfio``.

```shell
# VFIO support
CONFIG_IOMMU_SUPPORT=y
CONFIG_INTEL_IOMMU=y
CONFIG_INTEL_IOMMU_SVM=y
CONFIG_INTEL_IOMMU_DEFAULT_ON=y
CONFIG_IRQ_REMAP=y
CONFIG_VFIO=m
CONFIG_VFIO_PCI=m
CONFIG_VFIO_PCI_VGA=y
CONFIG_VFIO_PCI_IGD=y
CONFIG_VFIO_MDEV=m
CONFIG_VFIO_MDEV_DEVICE=m
CONFIG_PCI_PASID=y
CONFIG_PCI_PRI=y

CONFIG_SWIOTLB=y

CONFIG_VIRTIO_PMD=y
```

The userspace ethercat master stack provides ``dpdk-driver-bind.sh`` script, which is installed in ``/usr/sbin`` by default to be used to bind ``vfio`` driver for the EtherCAT port. 
Following command to bind vfio driver:

```shell
   dpdk-driver-bind.sh start <PCIe BDF address>
```

Following command to unbind vfio driver:

```shell
   dpdk-driver-bind.sh stop <PCIe BDF address>
```

### Running application

**For Daemon Mode**:

Following with below command to start daemon with specific master instance:

```shell
   ./master/ethercatd -m <master instance index>
```

**For Library Mode**:

Just start your application, which need request specific master instance index as below code, ``libecat`` will select specify EtherCAT port for using:

```shell
    static ec_master_t *master = NULL;
    static int master_id = 0;

    masters = ecrt_masters_create(0);
    master = ecrt_request_master(master_id);
    if (!master) {
        return -1;
    }
    ecrt_master_wait_for_slave(master, 1);

    ...

    if (ecrt_master_activate(master)) {
        return -1;
    }
```

### Makefile Template for EtherCAT application
-------------------------------------------

Provided below are some Makefile templates for EtherCAT application. These templates are provided to build EtherCAT application without ``Makefile.am``.

**Makefile template for Preempt-RT kernel**

**For Daemon Mode**:

```shell
      CC     = gcc
      CFLAGS = -Wall -O3 -g -D_GNU_SOURCE -D_REENTRANT -fasynchronous-unwind-tables
      LIBS   = -lm -lrt -lpthread -lethercat -Wl,--no-as-needed -L/usr/lib
      
      TARGET = test
      SRCS   = $(wildcard *.c)
      
      OBJS   = $(SRCS:.c=.o)
      
      $(TARGET):$(OBJS)
              $(CC) -o $@ $^ $(LIBS)
      
      clean:
              rm -rf $(TARGET) $(OBJS)
      
      %.o:%.c
              $(CC) $(CFLAGS) -o $@ -c $<
```

**For Library Mode**:

```shell
      CC     = gcc
      CFLAGS = -Wall -O3 -g -D_GNU_SOURCE -D_REENTRANT -fasynchronous-unwind-tables
      LIBS   = -lm -lrt -lpthread -lethercatd -Wl,--no-as-needed -L/usr/lib
      
      TARGET = test
      SRCS   = $(wildcard *.c)
      
      OBJS   = $(SRCS:.c=.o)
      
      $(TARGET):$(OBJS)
              $(CC) -o $@ $^ $(LIBS)
      
      clean:
              rm -rf $(TARGET) $(OBJS)
      
      %.o:%.c
              $(CC) $(CFLAGS) -o $@ -c $<
```

**Makefile template for Xenomai/Dovetail kernel(No supporte)**

### License

The source code is licensed under the GPL v2. See [COPYING](COPYING) file for details.