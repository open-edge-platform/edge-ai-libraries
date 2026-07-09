
### Introduction

This is a modular shell script installer for installing Open Edge platform components. For simplicity, all installable components or profiles are self-included within the installer script. In most of the cases, you can use the `curl | bash` pattern to simplify the download and installation process.    

### Bootstrapping

By default, the base installer does not contain any installable components. They are located under the directories: `module` or `profile`. Use the `boostrap` command to self-construct the final installer:

```
./openedge-cli bootstrap vision 
# ./openedge-cli bootstrap vision --default=vision  # install vision by default
```

After the bootstrap process, the `openedge-cli` shell script includes all the components specified by the `vision` profile and is ready to ship.  

### Installation

Install a component or a profile as follows:

```
./openedge-cli install vision
```

