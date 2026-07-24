
### Introduction

Components are installable modules within the OEP installer. Their filenames are in the pattern of `<component-name>/<OS_LIKE>`, where `<OS_LIKE>` is the OS family identifier (from `/etc/os-release`.) 
The component name should contain no whitespace or special character except '_'.  

### Develop a component

A component can be defined in optional shell functions: `<OS_LIKE>_<order>_<profile|install|remove|start|stop>_<component-name>`, where 
- `<OS_LIKE>`: The OS family identifier such as `debian`. You can get it from `/etc/os-release`.
- `<order>`: A number (prefixed with `0` if less than 10) from 0 to 99 to specify the installation order. The OEP installer will install components in the following order:

```
00-29   kernel modules/drivers
30-59   low level libraries
60-89   middle level libraries/microservices
90-98   applications
99      profiles
```

- `<start|stop|install|remove|profile>`: The `profile` function works similarly to a profile, which specifies the component dependencies, and the `install/remove/start/stop` functions perform their corresponding functions. At least one of thoses functions must be defined for the compoenent. Others are optional.

> For simple system-level packages, for example, `curl`, it is ok to define only an installation function without an uninstaller. The assumption is that `curl` can reside on the system for future use, while uninstalling it everytime is a bit overkill and may cause potentially unintended consequence. For other non-system components, there usually should define both an `install` function and a corresponding `remove` function. 

### Name Convention

Special care must be taken to write the shell functions such that there is no name collusion in both the function names and any used shell variables. 
It is a covention to always use local shell variables or prefix or suffix with the compoennt name. 



