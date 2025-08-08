# How to build EtherCAT with DKMS

## Introduction

**DKMS**(Dynamic Kernel Module Support) is a framework used to manage and automate the building and installation of kernel modules. It is particularly useful for handling out-of-tree modules that need to be rebuilt whenever the kernel is updated or changed. 

``dkms.conf`` is provided to support dkms as need, which contains the necessary configuration options for DKMS, you can adjust the values according to your module's specifics:

* ``PACKAGE_NAME``: The name of module.
* ``PACKAGE_VERSION``: The version of module.
* ``BUILT_MODULE_NAME``: The name of the module file that will be built.
* ``DEST_MODULE_LOCALTION``: The directory where the module will be installed.
* ``MAKE``: The compile command as you need.
* ``AUTOINSTALL``: Whether DKMS should automatically install the module after building.

## How to use DKMS

**Note**: The dkms command have to entered as root.

* Copy dkms.conf inside the module's source directory.

```shell
   cp dkms.conf ./ighethercat/.
```

* Add the module to DKMS

Use the following command to add your module to DKMS:

```shell
   dkms add -m <module_name> -v <module_version>
```

Replace ``<module_name>`` and ``<module_version>`` with the appropriate values from your ``dkms.conf``.

* Build the Module:

Once the module is added, you can build it using DKMS:

```shell
   dkms build -m <module_name> -v <module_version>
```

* Install the Module:

After building, install the module with:

```shell
   dkms install -m <module_name> -v <module_version>
```

* Verify Installation:

You can verify that the module is installed and loaded correctly using:

```shell
   lsmod | grep <module_name>
```

Or check the DKMS status:

```shell
   dkms status
```

If it have issues, please check ``/var/lib/dkms/<module_name>/<module_version>/build/make.log`` for details.

* Use DKMS to rebuild module

Sometime, you need rebuild module with some modifications after dkms installed. Following below commands to rebuild it.

```shell
   dkms uninstall -m <module_name> -v <module_version>
   
   dkms unbuild -m <module_name> -v <module_version>
   
   dkms build -m <module_name> -v <module_version>
   
   dkms install -m <module_name> -v <module_version>
```
