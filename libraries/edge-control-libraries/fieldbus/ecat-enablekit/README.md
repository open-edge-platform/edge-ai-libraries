Ecat_EnableKit
======================================


Overview
--------

**Ecat_EnableKit** is built on top of the IGH EtherCAT master stack and provides a simplified motion API for developing applications with various models of EtherCAT servo drives.

This version focuses on delivering a streamlined API and codebase, making it easier to integrate and use. Please note that the API is not backward compatible with previous versions or the original IGH EtherCAT master stack.

For detailed information, see the [Introduction](./docs/ecat_intro.md).

License
-------

LGPL v2.1

Dependencies
------------

    libxml2-dev

* For Ubuntu

```shell
    apt-get install libxml2-dev
```

Installation
------------

The shell commands are: 

```shell
    ./autogen.sh
    ./configure
    make
    make install
```

How to compile
-------------
* For Preempt-rt OS

```shell
    ./autogen.sh
```

    **Note:** If `libethercat.so` is not installed system-wide, use the following command to specify its location during the build process:

```shell
    ./autogen.sh LDFLAGS="-L<ethercat library path>"
    make
```

* For Xenomai/Dovetail OS

```shell
    autogen.sh --libdir=/usr/xenomai/lib --with-xenomai-dir=/usr/xenomai --with-xenomai-config=/usr/xenomai/bin/xeno-config
    make
```

Testing
-------
Some example tests are provided in [test-motionentry.c](./tests/test-motionentry.c). You can modify this source file to create custom test cases or adapt it to your specific requirements.



