
### Introduction

This is a modular shell script installer for installing Open Edge Platform components. For usability and simplicity, the installer shell script is self-contained to include all installable components and their dependencies. Profiles are defined as virtual groups of installable components.   

In most of the cases, you can use the `curl | bash` pattern to start the installation. In advacned usages, you can specify arguments: `curl | bash -s -- install smart_parking`.  

### Bootstrapping

By default, the base installer does not contain any installable components. They are located under the directories: `module` or `profile`. Use the `boostrap` command to self-construct the final installer:

```
./openedge-cli bootstrap vision 
# ./openedge-cli bootstrap --install=vision vision  # install vision by default

./rendered/openedge-cli bootstrap isv
# bundle the isv profile (and its dependencies) into a self-contained installer
```

After the bootstrap process, the `openedge-cli` shell script includes all the components specified by the `vision` profile and is ready to ship.  

### Installation and Removal

Install/remove a component or a profile as follows:

```
./rendered/openedge-cli install vision
./rendered/openedge-cli remove vision
```

### Start and Stop

Start and stop a component as follows:

```
./rendered/openedge-cli start smart_parking
./rendered/openedge-cli stop smart_parking
```

For install a ISV application, you can use the following commands:

```
./rendered/openedge-cli install unstructured   # a single component
./rendered/openedge-cli install isv             # every application in the isv profile
```

> If components within a profile are not compatible with each other, you cannot start/stop a profile. You can always start/stop a component directly.  




