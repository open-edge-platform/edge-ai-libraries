.. _real_time_linux:

Real-Time Linux
#################

|top_name| provides real-time capabilities to the kernel with PREEMPT_RT patch and boot parameters for real-time optimization, which aims to increase predictability and reduce scheduler latencies.

Installation
================

#. Before using the ECI repository, update the APT packages list:

   .. code-block:: bash

      $ sudo apt update

   .. figure:: assets/images/apt-update-1.png
      :align: center

   The APT package manager will download the latest list of packages available for all configured repositories.

   .. figure:: assets/images/apt-update-2.png
      :align: center

   .. tip::

      If the APT package manager is unable to connect to the repositories, follow these APT troubleshooting tips:

      * Make sure that the system has network connectivity.
      * Make sure that the ports ``80`` and ``8080`` are not blocked by a firewall.
      * Configure an APT proxy (if network traffic routes through a proxy server). To configure an APT proxy, add the following lines to a file at ``/etc/apt/apt.conf.d/proxy.conf`` (replace the placeholders as per your specific user and proxy server):

         .. code-block:: console

            Acquire::http::Proxy "http://user:password@proxy.server:port/";
            Acquire::https::Proxy "http://user:password@proxy.server:port/";

#. ECI provides Deb packages named ``customizations-*`` which add a GRUB menu entry for ECI and prepares the system to be deterministic. Install these packages using the ``eci-customizations`` meta-package:

   .. code-block:: bash

      $ sudo apt install -y eci-customizations

#. ECI provides a firmware package which backports updates from upstream to bring better hardware support to the current distribution. Install this package:

   .. code-block:: bash

      $ sudo apt-get reinstall '(firmware-linux-nonfree|linux-firmware$)'

#. Next, install the ECI real-time Linux kernel. There are two options available: Linux Intel LTS PREEMPT_RT kernel and Linux Intel LTS Xenomai Dovetail kernel. It is recommended that you start with **Linux Intel LTS PREEMPT_RT kernel**, if you do not know which option to choose.

   Click the corresponding tab to know more.

   .. tabs::

      .. group-tab:: Linux Intel LTS PREEMPT_RT Kernel

         **Linux Intel LTS PREEMPT_RT kernel** is Intel's Long-Term-Support kernel with PREEMPT_RT patches

         .. code-block:: bash

            $ sudo apt install -y linux-intel-rt

      .. group-tab:: Linux Intel LTS Xenomai Dovetail Kernel

         **Linux Intel LTS Xenomai Dovetail kernel** is Intel's Long-Term-Support kernel with Xenomai patches

         .. code-block:: bash

            $ sudo apt install -y eci-xenomai

   .. attention::

      Please review `Canonical Intellectual property rights policy <https://ubuntu.com/legal/intellectual-property-policy>`_ regarding |Ubuntu|. Note that any redistribution of modified versions of |Ubuntu| must be approved, certified or provided by Canonical if you are going to associate it with the Trademarks. Otherwise you must remove and replace the Trademarks and will need to recompile the source code to create your own binaries.

#. Reboot the target system.

   .. code-block:: bash

      $ sudo reboot

Verify Benchmark Performance
===============================

After installing the real-time Linux kernel, it's a good idea to benchmark the system to establish confidence that the system is properly configured. Perform either of the following commands to install `Cyclictest <https://git.kernel.org/pub/scm/utils/rt-tests/rt-tests.git>`_. Cyclictest is most commonly used for benchmarking real-time systems. It is one of the most frequently used tools for evaluating the relative performance of an RT. Cyclictest accurately and repeatedly measures the difference between a thread’s intended wake-up time and the time at which it actually wakes up to provide statistics about the system’s latency. It can measure latency in real-time systems caused by the hardware, the firmware, and the operating system.
Please use ``rt-tests v2.6`` to collect performance, which support to pin threads to specific isolate core and avoid main thread in same core with the measurement threads.

Follow with below steps, you can find ``cyclictest v2.6`` in ``rt-tests-2.6``：

.. code-block:: bash

    $ wget https://web.git.kernel.org/pub/scm/utils/rt-tests/rt-tests.git/snapshot/rt-tests-2.6.tar.gz
    $ tar zxvf rt-tests-2.6.tar.gz
    $ cd rt-tests-2.6
    $ make

**Note**: Please ensure you had installed ``libnuma-dev`` as dependence before compilation.

  .. code-block:: bash

     $ sudo apt install libnuma-dev

An example command that runs the cyclictest benchmark as below:

.. code-block:: bash

    $ cyclictest -mp 99 -t1 -a 13 -i 1000 --laptop -D 72h  -N --mainaffinity 12

Default parameters are used unless otherwise specified. Run ``cyclictest --help`` to list the modifiable arguments.

.. list-table::
   :widths: 50 500
   :header-rows: 1

   * - option
     - Explanation
   * - -p
     - priority of highest priority thread
   * - -t
     - one thread per available processor
   * - -a
     - Run thread #N on processor #N, or if CPUSET given, pin threads to that set of processors in round-robin order
   * - -i
     - base interval of thread in us default=1000
   * - -D
     - specify a length for the test run
   * - -N
     - print results in ns instead of us(default us)
   * - --mainaffinity
     - Run the main thread on CPU #N. This only affects the main thread and not the measurement threads
   * - -m
     - lock current and future memory allocations
   * - --laptop
     - Not setting ``cpu_dma_latency`` to save battery, recommend using it when enabling per-core C-state disable.  

On a **realtime-enabled** system, the result might be similar to the following:

.. code-block:: console

    T: 0 ( 3407) P:99 I:1000 C: 100000 Min:      928 Act:   1376 Avg:   1154 Max:      18373

This result indicates an apparent short-term worst-case latency of 18 us. According to this, it is important to pay attention to the Max values as these are indicators of outliers. Even if the system has decent Avg (average) values, a single outlier as indicated by Max is enough to break or disturb a real-time system.

If the real-time data is not good by default installation, please refer to :ref:`OS Setup <OS_Setup>` for BIOS optimization and `Optimize Performance <https://eci.intel.com/docs/3.3/development/performance.html>`_ to optimize Linux OS and application runtime on |Intel| Processors.
