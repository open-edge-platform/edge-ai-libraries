
### Introduction

Profiles are virtual groups of installer components. The profile filenames use this pattern: `<profile-name>/<OS_LIKE>`, where `<OS_LIKE>` is the OS family identifier obtained from `/etc/os-release`, 
and the profile name should contain no space or special character except `_`.  

### Develop a Profile

A profile specifies the list of required components in a single shell function: `<OS_LIKE>_<order>_<name>`, where `<order>` specifies the installation order. Since profiles are virtual groups, they always use order `99` to install the latest. 

A profile can be as simple as follows:

```
debian_99_metro_ai_suites () {
  echo "smart_parking smart_intersection loitering_detection"
}
```
where each component is listed at the output.  

In the above sample, if we want to specify that the components can install/remove togeher but not start/stop together, we can make it conditioned on the installer subcommand:

```
debian_99_metro_ai_suites () {
  case "$1" in
  install/remove)
    echo "smart_parking smart_intersection loitering_detection"
    ;;
  esac
}
```
